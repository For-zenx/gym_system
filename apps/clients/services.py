import base64
import os
from datetime import date

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Exists, Max, OuterRef
from django.db.models.functions import Coalesce

from apps.billing.models import Membership

from .models import Client, GuestPass, PERSON_CODE_PREFIX, PersonCategory

ALLOWED_INACTIVITY_YEARS = (1, 2)
INACTIVE_CLIENTS_PREVIEW_LIMIT = 20


class BulkDeleteCountMismatchError(Exception):
    def __init__(self, actual_count):
        self.actual_count = actual_count
        super().__init__(actual_count)

CLIENT_IMAGE_FIELDS = ("foto_frente", "foto_perfil_izq", "foto_perfil_der")


def get_next_person_code(category):
    if category not in PERSON_CODE_PREFIX:
        raise ValueError("Invalid person category")

    prefix = PERSON_CODE_PREFIX[category]
    max_num = 0
    for code in Client.objects.filter(
        codigo_afiliado__startswith="{}-".format(prefix)
    ).values_list("codigo_afiliado", flat=True):
        parts = code.split("-")
        if len(parts) >= 2 and parts[0] == prefix:
            try:
                max_num = max(max_num, int(parts[1]))
            except ValueError:
                continue
    return "{}-{:05d}-00".format(prefix, max_num + 1)


def get_person_profile_url_name(client):
    if client.person_category == PersonCategory.MEMBER:
        return "clients:profile"
    if client.person_category == PersonCategory.GUEST:
        return "guests:profile"
    return "staff_persons:profile"


def guest_pass_is_valid(guest_pass, on_date=None):
    if on_date is None:
        on_date = date.today()
    if guest_pass.revoked_at:
        return False
    return guest_pass.valid_from <= on_date <= guest_pass.valid_until


def get_active_guest_pass(client, on_date=None):
    if on_date is None:
        on_date = date.today()
    if not client.is_guest:
        return None
    return (
        GuestPass.objects.filter(
            guest=client,
            revoked_at__isnull=True,
            valid_from__lte=on_date,
            valid_until__gte=on_date,
        )
        .select_related("sponsor")
        .order_by("-valid_until", "-created_at")
        .first()
    )


def _apply_guest_client_fields(client, cleaned):
    client.nombre = cleaned["nombre"]
    client.cedula = cleaned["cedula"]
    client.telefono = cleaned["telefono"] or None
    client.fecha_nacimiento = cleaned["fecha_nacimiento"]
    client.sexo = cleaned["sexo"]
    client.person_category = PersonCategory.GUEST


@transaction.atomic
def issue_guest_pass(guest, sponsor, valid_from, valid_until, registered_by=None, notes=""):
    if not guest.is_guest:
        raise ValueError("Solo los invitados pueden recibir pases de invitado.")
    if sponsor is not None and not sponsor.is_member:
        raise ValueError("El responsable debe ser un afiliado.")
    return GuestPass.objects.create(
        guest=guest,
        sponsor=sponsor,
        valid_from=valid_from,
        valid_until=valid_until,
        registered_by=registered_by,
        notes=(notes or "").strip(),
    )


@transaction.atomic
def create_guest_with_pass(
    sponsor,
    cleaned_data,
    valid_from,
    valid_until,
    registered_by=None,
    notes="",
    foto_frente_b64=None,
):
    if sponsor is not None and not sponsor.is_member:
        raise ValueError("El responsable debe ser un afiliado.")

    codigo = get_next_person_code(PersonCategory.GUEST)
    guest = Client(codigo_afiliado=codigo)
    _apply_guest_client_fields(guest, cleaned_data)
    guest.save()

    guest_pass = issue_guest_pass(
        guest,
        sponsor,
        valid_from,
        valid_until,
        registered_by=registered_by,
        notes=notes,
    )

    if foto_frente_b64:
        apply_front_photo_from_b64(guest, foto_frente_b64)

    return guest, guest_pass


@transaction.atomic
def revoke_guest_pass(guest_pass):
    from django.utils import timezone

    if guest_pass.revoked_at:
        return guest_pass
    guest_pass.revoked_at = timezone.now()
    guest_pass.save(update_fields=["revoked_at"])
    return guest_pass


def get_guest_feed_lines(client):
    active = get_active_guest_pass(client)
    if active:
        return [
            {
                "status": "active",
                "title": "Pase de invitado",
                "primary": "Vigente hasta {}".format(active.valid_until.strftime("%d/%m/%Y")),
                "secondary": (
                    "Responsable: {}".format(active.sponsor.nombre)
                    if active.sponsor_id
                    else None
                ),
            }
        ]
    return [
        {
            "status": "empty",
            "title": "Sin pase activo",
            "primary": None,
            "secondary": None,
        }
    ]


def _content_file_from_b64(b64_str, filename_base):
    if not b64_str:
        return None
    format_part, imgstr = b64_str.split(";base64,")
    ext = format_part.split("/")[-1]
    full_filename = f"{filename_base}.{ext}"
    storage_path = f"clients/enrollment/{full_filename}"
    if default_storage.exists(storage_path):
        default_storage.delete(storage_path)
    return ContentFile(base64.b64decode(imgstr), name=full_filename)


def apply_front_photo_from_b64(client, foto_frente_b64):
    from apps.access import ai_engine

    frente_file = _content_file_from_b64(foto_frente_b64, f"{client.codigo_afiliado}_frente")
    if not frente_file:
        raise ValueError("La foto capturada no es válida.")

    if client.foto_frente:
        client.foto_frente.delete(save=False)

    client.foto_frente = frente_file
    client.save(update_fields=["foto_frente"])
    ai_engine.update_client_embeddings(client)
    return client


def replace_client_front_photo(client, foto_frente_b64):
    return apply_front_photo_from_b64(client, foto_frente_b64)


def _delete_client_image_files(client):
    for field_name in CLIENT_IMAGE_FIELDS:
        image_field = getattr(client, field_name, None)
        if image_field:
            image_field.delete(save=False)


@transaction.atomic
def delete_client(client):
    codigo_afiliado = client.codigo_afiliado
    _delete_client_image_files(client)
    # Periodos de servicio referencian Membership con PROTECT; deben ir antes del cascade del afiliado.
    client.service_periods.all().delete()
    client.delete()
    return codigo_afiliado


def _subtract_years(from_date, years):
    try:
        return from_date.replace(year=from_date.year - years)
    except ValueError:
        return from_date.replace(year=from_date.year - years, month=2, day=28)


def get_inactive_clients_queryset(inactivity_years, today=None):
    if inactivity_years not in ALLOWED_INACTIVITY_YEARS:
        raise ValueError("Invalid inactivity years")

    if today is None:
        today = date.today()

    cutoff = _subtract_years(today, inactivity_years)
    active_membership = Membership.objects.filter(
        client=OuterRef("pk"),
        fecha_inicio__lte=today,
        fecha_fin__gte=today,
    )
    queued_membership = Membership.objects.filter(
        client=OuterRef("pk"),
        fecha_inicio__gt=today,
    )

    return (
        Client.objects.filter(person_category=PersonCategory.MEMBER)
        .annotate(last_membership_end=Max("memberships__fecha_fin"))
        .annotate(inactivity_anchor=Coalesce("last_membership_end", "fecha_ingreso"))
        .exclude(Exists(active_membership))
        .exclude(Exists(queued_membership))
        .filter(inactivity_anchor__lte=cutoff)
        .order_by("inactivity_anchor", "nombre", "id")
    )


def build_inactive_clients_preview(inactivity_years, today=None):
    queryset = get_inactive_clients_queryset(inactivity_years, today=today)
    count = queryset.count()
    sample_rows = list(
        queryset[:INACTIVE_CLIENTS_PREVIEW_LIMIT].values(
            "nombre",
            "codigo_afiliado",
            "cedula",
            "inactivity_anchor",
        )
    )
    sample = []
    for row in sample_rows:
        anchor = row.pop("inactivity_anchor")
        sample.append(
            {
                "nombre": row["nombre"],
                "codigo_afiliado": row["codigo_afiliado"],
                "cedula": row["cedula"],
                "inactivity_since": anchor.strftime("%d/%m/%Y") if anchor else "",
            }
        )

    return {
        "count": count,
        "sample": sample,
        "sample_truncated": count > INACTIVE_CLIENTS_PREVIEW_LIMIT,
        "inactivity_years": inactivity_years,
    }


@transaction.atomic
def bulk_delete_inactive_clients(inactivity_years, expected_count, today=None):
    queryset = get_inactive_clients_queryset(inactivity_years, today=today)
    actual_count = queryset.count()
    if actual_count != expected_count:
        raise BulkDeleteCountMismatchError(actual_count)

    deleted_codes = []
    for client in list(queryset):
        deleted_codes.append(delete_client(client))
    return deleted_codes


def save_enrollment_photos(client, files_dict):
    """
    Guarda las 3 fotos de enrolamiento en media/clients/{id}/.
    Sobreescribe las existentes si el afiliado se está re-enrolando.
    files_dict: {'frente': file, 'izquierda': file, 'derecha': file}
    """
    client_folder = os.path.join('clients', str(client.id))
    full_path = os.path.join(settings.MEDIA_ROOT, client_folder)

    # Asegurar que la carpeta del cliente exista
    if not os.path.exists(full_path):
        os.makedirs(full_path)

    for side, uploaded_file in files_dict.items():
        if side not in ['frente', 'izquierda', 'derecha']:
            continue
        
        filename = f"{side}.jpg"
        file_path = os.path.join(full_path, filename)

        # Borrar archivo anterior si existe (re-enrolamiento)
        if os.path.exists(file_path):
            os.remove(file_path)

        # Guardar el nuevo archivo
        with open(file_path, 'wb+') as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)
        
        # Guardar la referencia de la foto principal (frente) en el modelo
        if side == 'frente':
            client.foto = os.path.join(client_folder, filename)
            client.save()

    return True

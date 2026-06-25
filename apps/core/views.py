from datetime import date, timedelta

from functools import wraps

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from apps.clients.models import Client, PersonCategory
from apps.clients.validation import (
    validate_client_data,
    validate_guest_enrollment_data,
    validate_guest_pass_dates,
    client_form_context,
    build_cedula,
)
from apps.clients.services import (
    apply_front_photo_from_b64,
    create_guest_with_pass,
    get_next_person_code,
    get_person_profile_url_name,
)
from apps.access.models import AccessLog
from apps.users.decorators import permission_required
from apps.users.permissions import has_permission


STAFF_ENROLLMENT_CATEGORIES = (
    PersonCategory.EMPLOYEE,
    PersonCategory.TRAINER,
)

ENROLLMENT_TIPO_MAP = {
    "afiliado": PersonCategory.MEMBER,
    "empleado": PersonCategory.EMPLOYEE,
    "entrenador": PersonCategory.TRAINER,
    "invitado": PersonCategory.GUEST,
}


def get_next_codigo_afiliado():
    return get_next_person_code(PersonCategory.MEMBER)


def _enrollment_wants_json(request):
    return request.headers.get("X-Enrollment-Submit") == "1"


def _user_can_enroll_category(user, category):
    if category == PersonCategory.MEMBER:
        return has_permission(user, "clients.enroll")
    if category == PersonCategory.GUEST:
        return has_permission(user, "guests.register")
    if category in STAFF_ENROLLMENT_CATEGORIES:
        return has_permission(user, "staff_persons.enroll")
    return False


def _enrollment_access_denied(request):
    if _enrollment_wants_json(request):
        return JsonResponse({"status": "error", "message": "No tienes permiso para enrolar."}, status=403)
    raise PermissionDenied("No tienes permiso para enrolar.")


def _resolve_enrollment_category(request, post_data=None):
    source = post_data if post_data is not None else request.POST
    raw = source.get("person_category") if source else None
    if not raw:
        tipo = request.GET.get("tipo", "")
        raw = ENROLLMENT_TIPO_MAP.get(tipo)
    if raw in (PersonCategory.MEMBER, PersonCategory.EMPLOYEE, PersonCategory.TRAINER, PersonCategory.GUEST):
        if _user_can_enroll_category(request.user, raw):
            return raw
    if has_permission(request.user, "clients.enroll"):
        return PersonCategory.MEMBER
    if has_permission(request.user, "guests.register"):
        return PersonCategory.GUEST
    return PersonCategory.EMPLOYEE


def _enrollment_page_context(request, post_data=None, person_category=None):
    if person_category is None:
        person_category = _resolve_enrollment_category(request, post_data)
    context = client_form_context(post_data=post_data)
    context["person_category"] = person_category
    context["can_enroll_member"] = has_permission(request.user, "clients.enroll")
    context["can_enroll_staff"] = has_permission(request.user, "staff_persons.enroll")
    context["can_enroll_guest"] = has_permission(request.user, "guests.register")
    today = date.today()
    context["default_valid_from"] = today.isoformat()
    context["default_valid_until"] = (today + timedelta(days=1)).isoformat()
    if post_data is not None:
        if post_data.get("valid_from"):
            context["default_valid_from"] = post_data.get("valid_from")
        if post_data.get("valid_until"):
            context["default_valid_until"] = post_data.get("valid_until")
        context["form_notes"] = post_data.get("notes", "")
    else:
        context["form_notes"] = ""
    return context


def _enrollment_error_response(request, message, post_data=None, status=400):
    if _enrollment_wants_json(request):
        return JsonResponse({"status": "error", "message": message}, status=status)
    messages.error(request, message)
    category = _resolve_enrollment_category(request, post_data)
    return render(
        request,
        "enrollment.html",
        _enrollment_page_context(request, post_data=post_data, person_category=category),
    )


def enrollment_access(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (
            has_permission(request.user, "clients.enroll")
            or has_permission(request.user, "staff_persons.enroll")
            or has_permission(request.user, "guests.register")
        ):
            return _enrollment_access_denied(request)
        return view_func(request, *args, **kwargs)

    return wrapper


@enrollment_access
def enrollment_cedula_check(request):
    cedula = build_cedula(
        request.GET.get("cedula_prefix"),
        request.GET.get("cedula_numero"),
    )
    client = Client.objects.filter(cedula=cedula).first()
    profile_url = None
    re_enroll_url = None
    if client:
        profile_url = reverse(
            get_person_profile_url_name(client),
            kwargs={"codigo_afiliado": client.codigo_afiliado},
        )
        re_enroll_url = reverse("clients:re_enroll", kwargs={"codigo_afiliado": client.codigo_afiliado})
    return JsonResponse({
        "exists": bool(client),
        "profile_url": profile_url,
        "re_enroll_url": re_enroll_url,
        "person_category": client.person_category if client else None,
    })


@login_required
@permission_required("dashboard.view")
def dashboard(request):
    latest_logs = AccessLog.objects.select_related("client").order_by("-timestamp")[:4]
    return render(request, "dashboard.html", {"logs": latest_logs})


@enrollment_access
def enrollment(request):
    person_category = _resolve_enrollment_category(request)

    if request.method == "POST":
        person_category = _resolve_enrollment_category(request, request.POST)
        if not _user_can_enroll_category(request.user, person_category):
            return _enrollment_access_denied(request)

        foto_frente_b64 = request.POST.get("foto_frente_base64")
        if not foto_frente_b64:
            return _enrollment_error_response(
                request,
                "Debe capturar la foto en la tablet de enrolamiento.",
                post_data=request.POST,
            )

        if person_category == PersonCategory.GUEST:
            errors, cleaned = validate_guest_enrollment_data(request.POST.get("nombre"))
            pass_errors, pass_cleaned = validate_guest_pass_dates(
                request.POST.get("valid_from"),
                request.POST.get("valid_until"),
            )
            errors.update(pass_errors)
            if errors:
                first_error = next(iter(errors.values()))
                if _enrollment_wants_json(request):
                    return JsonResponse({"status": "error", "message": first_error}, status=400)
                for message in errors.values():
                    messages.error(request, message)
                return render(
                    request,
                    "enrollment.html",
                    _enrollment_page_context(request, post_data=request.POST, person_category=person_category),
                )

            notes = (request.POST.get("notes") or "").strip()
            try:
                guest, _guest_pass = create_guest_with_pass(
                    sponsor=None,
                    cleaned_data=cleaned,
                    valid_from=pass_cleaned["valid_from"],
                    valid_until=pass_cleaned["valid_until"],
                    registered_by=request.user,
                    notes=notes,
                    foto_frente_b64=foto_frente_b64,
                )
            except Exception as exc:
                return _enrollment_error_response(
                    request,
                    "No se pudo registrar el invitado: {}".format(exc),
                    post_data=request.POST,
                )

            redirect_target = reverse(
                "guests:profile",
                kwargs={"codigo_afiliado": guest.codigo_afiliado},
            )
            if _enrollment_wants_json(request):
                return JsonResponse({"status": "success", "redirect_url": redirect_target})
            messages.success(request, "Invitado {} registrado correctamente.".format(guest.nombre))
            return redirect(redirect_target)

        errors, cleaned = validate_client_data(
            request.POST.get("nombre"),
            request.POST.get("cedula_prefix"),
            request.POST.get("cedula_numero"),
            request.POST.get("telefono"),
            request.POST.get("fecha_nacimiento"),
            request.POST.get("sexo"),
        )

        if errors:
            first_error = next(iter(errors.values()))
            if _enrollment_wants_json(request):
                return JsonResponse({"status": "error", "message": first_error}, status=400)
            for message in errors.values():
                messages.error(request, message)
            return render(
                request,
                "enrollment.html",
                _enrollment_page_context(request, post_data=request.POST, person_category=person_category),
            )

        cedula = cleaned["cedula"]
        nombre = cleaned["nombre"]

        if not foto_frente_b64:
            return _enrollment_error_response(
                request,
                "Debe capturar la foto en la tablet de enrolamiento.",
                post_data=request.POST,
            )

        existing = Client.objects.filter(cedula=cedula).first()
        if existing:
            if person_category == PersonCategory.MEMBER:
                if existing.is_staff_person:
                    return _enrollment_error_response(
                        request,
                        "Esta cédula pertenece a personal del gimnasio. No puede enrolarse como afiliado.",
                        post_data=request.POST,
                    )
                return _enrollment_error_response(
                    request,
                    "Este afiliado ya está registrado. Use Re-enrolar desde su perfil si necesita actualizar la foto facial.",
                    post_data=request.POST,
                )
            if existing.is_member:
                return _enrollment_error_response(
                    request,
                    "Esta cédula pertenece a un afiliado. No puede registrarse como personal.",
                    post_data=request.POST,
                )
            return _enrollment_error_response(
                request,
                "Esta cédula ya está registrada como personal del gimnasio.",
                post_data=request.POST,
            )

        if person_category == PersonCategory.MEMBER and request.POST.get("terms_accepted") != "1":
            return _enrollment_error_response(
                request,
                "El afiliado debe aceptar los términos y condiciones en la tablet.",
                post_data=request.POST,
            )

        try:
            codigo = get_next_person_code(person_category)
            client_kwargs = {
                "cedula": cedula,
                "nombre": nombre,
                "telefono": cleaned["telefono"] or None,
                "fecha_nacimiento": cleaned["fecha_nacimiento"],
                "sexo": cleaned["sexo"],
                "codigo_afiliado": codigo,
                "person_category": person_category,
            }
            if person_category == PersonCategory.MEMBER:
                client_kwargs["terms_accepted_at"] = timezone.now()
            client = Client(**client_kwargs)
            client.save()

            try:
                apply_front_photo_from_b64(client, foto_frente_b64)
            except Exception as exc:
                client.delete()
                return _enrollment_error_response(
                    request,
                    "No se pudo procesar la foto facial: {}".format(exc),
                    post_data=request.POST,
                )

            if person_category == PersonCategory.MEMBER:
                checkout_url = reverse(
                    "billing:charge_checkout",
                    kwargs={"codigo_afiliado": client.codigo_afiliado},
                )
                redirect_target = "{}?origin=enrollment".format(checkout_url)
            else:
                redirect_target = reverse(
                    "staff_persons:profile",
                    kwargs={"codigo_afiliado": client.codigo_afiliado},
                )

            if _enrollment_wants_json(request):
                return JsonResponse({"status": "success", "redirect_url": redirect_target})
            if person_category == PersonCategory.MEMBER:
                messages.success(request, "Afiliado {} guardado exitosamente.".format(nombre))
            else:
                messages.success(request, "{} registrado correctamente.".format(nombre))
            return redirect(redirect_target)
        except Exception as exc:
            return _enrollment_error_response(
                request,
                "Error al guardar: {}".format(exc),
                post_data=request.POST,
            )

    return render(
        request,
        "enrollment.html",
        _enrollment_page_context(request, person_category=person_category),
    )


@login_required
@permission_required("clients.enroll")
def enrollment_billing(request, codigo_afiliado):
    client = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)
    if not client.can_purchase_membership:
        messages.error(request, "Solo los afiliados pueden usar el cobro de enrolamiento.")
        return redirect(
            reverse(
                get_person_profile_url_name(client),
                kwargs={"codigo_afiliado": codigo_afiliado},
            )
        )
    checkout_url = reverse(
        "billing:charge_checkout",
        kwargs={"codigo_afiliado": codigo_afiliado},
    )
    return redirect("{}?origin=enrollment".format(checkout_url))


@login_required
def staff_person_enrollment(request):
    tipo = request.GET.get("tipo", "empleado")
    if tipo not in ENROLLMENT_TIPO_MAP:
        tipo = "empleado"
    return redirect("{}?tipo={}".format(reverse("enrollment"), tipo))

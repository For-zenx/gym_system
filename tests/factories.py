import itertools
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model

from apps.billing.models import Invoice, InvoiceLine, Membership, Plan, SaleItem, ExchangeRate
from apps.clients.models import Client, PERSON_CODE_PREFIX, PersonCategory
from apps.lockers.models import Locker
from apps.users.models import StaffProfile, StaffRole
from apps.users.permissions import validate_permissions

User = get_user_model()

_user_counter = itertools.count(1)
_client_counter = itertools.count(1)
_plan_counter = itertools.count(1)
_sale_item_counter = itertools.count(1)
_role_counter = itertools.count(1)
_invoice_counter = itertools.count(1)
_locker_counter = itertools.count(1)


def create_staff_user(permissions=None, username=None, password="testpass123", is_superuser=False):
    seq = next(_user_counter)
    if username is None:
        username = "staff_{}".format(seq)

    user = User.objects.create_user(
        username=username,
        password=password,
        is_superuser=is_superuser,
    )
    if is_superuser:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
        return user

    validated = validate_permissions(permissions or [])
    if validated:
        StaffProfile.objects.create(
            user=user,
            display_name="Staff {}".format(seq),
            permissions=validated,
        )
    # Sin permisos validados: usuario autenticable sin StaffProfile (equivale a permisos vacíos).
    return user


def create_client(cedula=None, nombre=None, codigo_afiliado=None, telefono=None, person_category=PersonCategory.MEMBER):
    seq = next(_client_counter)
    prefix = PERSON_CODE_PREFIX.get(person_category, "M")
    return Client.objects.create(
        cedula=cedula or "V-{:08d}".format(seq),
        nombre=nombre or "Afiliado Test {}".format(seq),
        codigo_afiliado=codigo_afiliado or "{}-{:05d}-00".format(prefix, seq),
        telefono=telefono,
        person_category=person_category,
    )


def create_plan(nombre=None, billing_type=Plan.BillingType.FLEXIBLE, dias_duracion=30, precio_usd=None):
    seq = next(_plan_counter)
    return Plan.objects.create(
        nombre=nombre or "Plan Test {}".format(seq),
        billing_type=billing_type,
        dias_duracion=dias_duracion if billing_type == Plan.BillingType.FLEXIBLE else None,
        precio_usd=precio_usd or Decimal("10.00"),
        is_active=True,
    )


def create_sale_item(
    name=None,
    item_type=SaleItem.ItemType.PRODUCT,
    price_usd=None,
    requires_locker_assignment=False,
    system_code=None,
):
    seq = next(_sale_item_counter)
    return SaleItem.objects.create(
        name=name or "Producto Test {}".format(seq),
        item_type=item_type,
        price_usd=price_usd or Decimal("5.00"),
        requires_locker_assignment=requires_locker_assignment,
        system_code=system_code,
        is_active=True,
    )


def create_exchange_rate(tasa_ves=None):
    return ExchangeRate.objects.create(tasa_ves=tasa_ves or Decimal("50.00"))


def create_locker(number=None, status=Locker.Status.AVAILABLE):
    seq = next(_locker_counter)
    return Locker.objects.create(
        number=number or "L-{:03d}".format(seq),
        status=status,
    )


def get_or_create_locker_rental_item():
    item = SaleItem.get_locker_rental_item()
    if item:
        return item
    return SaleItem.objects.create(
        name="Alquiler de casillero",
        item_type=SaleItem.ItemType.SERVICE,
        price_usd=Decimal("5.00"),
        requires_locker_assignment=True,
        system_code=SaleItem.SystemCode.LOCKER_RENTAL,
        is_active=True,
    )


def create_staff_role(name=None, permissions=None):
    seq = next(_role_counter)
    return StaffRole.objects.create(
        name=name or "Plantilla Test {}".format(seq),
        permissions=validate_permissions(permissions or ["plans.view"]),
    )


def create_membership(client=None, plan=None, fecha_inicio=None, fecha_fin=None):
    if client is None:
        client = create_client()
    if plan is None:
        plan = create_plan(billing_type=Plan.BillingType.FLEXIBLE, dias_duracion=30)
    if fecha_inicio is None:
        fecha_inicio = date.today()
    if fecha_fin is None:
        duration = plan.dias_duracion or 30
        fecha_fin = fecha_inicio + timedelta(days=duration)
    return Membership.objects.create(
        client=client,
        plan=plan,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )


def create_invoice(
    client=None,
    plan=None,
    with_line=False,
    nro_control=None,
    monto_total=None,
    esta_impresa=False,
):
    if client is None:
        client = create_client()
    if plan is None:
        plan = create_plan()

    membership = Membership.objects.create(
        client=client,
        plan=plan,
        fecha_inicio=date.today(),
    )
    seq = next(_invoice_counter)
    total = monto_total or Decimal("1000.00")
    invoice = Invoice.objects.create(
        client=client,
        membership=membership,
        monto_total=total,
        nro_control=nro_control or "TEST-{:05d}".format(seq),
        esta_impresa=esta_impresa,
        plan_snapshot=plan.nombre,
    )
    invoice.set_client_snapshots(client)
    invoice.save(
        update_fields=[
            "client_nombre_snapshot",
            "client_cedula_snapshot",
            "client_codigo_snapshot",
            "plan_snapshot",
        ]
    )

    if with_line:
        InvoiceLine.objects.create(
            invoice=invoice,
            line_kind=InvoiceLine.LineKind.MEMBERSHIP,
            description=plan.nombre,
            amount_ves=total,
            membership=membership,
            unit_price_usd=plan.precio_usd,
        )

    return invoice

import itertools
from decimal import Decimal

from django.contrib.auth import get_user_model

from apps.billing.models import Plan, SaleItem
from apps.clients.models import Client
from apps.users.models import StaffProfile
from apps.users.permissions import validate_permissions

User = get_user_model()

_user_counter = itertools.count(1)
_client_counter = itertools.count(1)
_plan_counter = itertools.count(1)
_sale_item_counter = itertools.count(1)


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


def create_client(cedula=None, nombre=None, codigo_afiliado=None, telefono=None):
    seq = next(_client_counter)
    return Client.objects.create(
        cedula=cedula or "V-{:08d}".format(seq),
        nombre=nombre or "Afiliado Test {}".format(seq),
        codigo_afiliado=codigo_afiliado or "M-{:05d}-00".format(seq),
        telefono=telefono,
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


def create_sale_item(name=None, item_type=SaleItem.ItemType.PRODUCT, price_usd=None):
    seq = next(_sale_item_counter)
    return SaleItem.objects.create(
        name=name or "Producto Test {}".format(seq),
        item_type=item_type,
        price_usd=price_usd or Decimal("5.00"),
        is_active=True,
    )

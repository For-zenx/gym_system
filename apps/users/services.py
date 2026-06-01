from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import StaffProfile, StaffRole
from .permissions import (
    ADMIN_CAPACITY_PERMISSIONS,
    ADMINISTRATOR_PERMISSION_CODES,
    validate_permissions,
)

User = get_user_model()


def copy_permissions_from_role(role):
    if role is None:
        return []
    return validate_permissions(role.permissions or [])


def get_or_create_staff_profile(user):
    profile, created = StaffProfile.objects.get_or_create(
        user=user,
        defaults={
            "display_name": user.get_full_name() or user.username,
            "permissions": [],
        },
    )
    return profile


def update_staff_permissions(profile, codes):
    profile.permissions = validate_permissions(codes)
    profile.save(update_fields=["permissions", "updated_at"])
    return profile


def apply_template_to_profile(profile, role):
    profile.permissions = copy_permissions_from_role(role)
    profile.created_from_role = role
    profile.save(update_fields=["permissions", "created_from_role", "updated_at"])
    return profile


def _active_users_with_staff_profile(excluding_user_id=None):
    queryset = User.objects.filter(is_active=True).select_related("staff_profile")
    if excluding_user_id is not None:
        queryset = queryset.exclude(pk=excluding_user_id)
    return queryset


def user_has_admin_capacity(user):
    if user.is_superuser:
        return True
    profile = getattr(user, "staff_profile", None)
    if profile is None:
        return False
    perms = set(profile.permissions or [])
    return ADMIN_CAPACITY_PERMISSIONS.issubset(perms)


def count_admin_capable_users(excluding_user_id=None):
    count = 0
    for user in _active_users_with_staff_profile(excluding_user_id=excluding_user_id):
        if user_has_admin_capacity(user):
            count += 1
    return count


def ensure_admin_capacity_preserved(
    *,
    excluding_user_id=None,
    proposed_permissions=None,
    proposed_is_active=True,
    target_user_id=None,
):
    """
    Impide dejar el sistema sin al menos un usuario activo con capacidad de administración.
    """
    if proposed_is_active is False and target_user_id is not None:
        target = User.objects.filter(pk=target_user_id).select_related("staff_profile").first()
        if target and user_has_admin_capacity(target):
            if count_admin_capable_users(excluding_user_id=target_user_id) < 1:
                raise ValidationError(
                    "No se puede desactivar al último usuario con acceso de administración."
                )
        return

    if proposed_permissions is not None and target_user_id is not None:
        proposed = set(validate_permissions(proposed_permissions))
        if not ADMIN_CAPACITY_PERMISSIONS.issubset(proposed):
            target = User.objects.filter(pk=target_user_id).select_related("staff_profile").first()
            if target and user_has_admin_capacity(target):
                if count_admin_capable_users(excluding_user_id=target_user_id) < 1:
                    raise ValidationError(
                        "No se pueden quitar permisos de administración al último usuario capacitado."
                    )


def resolve_permissions_for_new_user(template_role=None, permissions=None):
    if permissions is not None:
        return validate_permissions(permissions)
    if template_role is not None:
        return copy_permissions_from_role(template_role)
    return []


@transaction.atomic
def create_staff_user(
    username,
    password,
    display_name,
    permissions=None,
    template_role=None,
    is_active=True,
):
    username = (username or "").strip()
    display_name = (display_name or "").strip()
    if not username:
        raise ValidationError("El nombre de usuario es obligatorio.")
    if not display_name:
        raise ValidationError("El nombre visible es obligatorio.")
    if User.objects.filter(username=username).exists():
        raise ValidationError("Ese nombre de usuario ya existe.")

    validate_password(password)

    effective_permissions = resolve_permissions_for_new_user(
        template_role=template_role,
        permissions=permissions,
    )

    user = User.objects.create_user(
        username=username,
        password=password,
        is_staff=False,
        is_superuser=False,
        is_active=is_active,
    )
    StaffProfile.objects.create(
        user=user,
        display_name=display_name,
        permissions=effective_permissions,
        created_from_role=template_role,
    )
    return user


@transaction.atomic
def update_staff_user(
    user,
    *,
    display_name=None,
    password=None,
    permissions=None,
    template_role=None,
    is_active=None,
    acting_user=None,
):
    if acting_user and acting_user.pk == user.pk and is_active is False:
        raise ValidationError("No puedes desactivar tu propia cuenta.")

    profile = get_or_create_staff_profile(user)

    if display_name is not None:
        display_name = display_name.strip()
        if not display_name:
            raise ValidationError("El nombre visible es obligatorio.")
        profile.display_name = display_name

    if template_role is not None and permissions is None:
        apply_template_to_profile(profile, template_role)
    elif permissions is not None:
        ensure_admin_capacity_preserved(
            proposed_permissions=permissions,
            proposed_is_active=is_active if is_active is not None else user.is_active,
            target_user_id=user.pk,
        )
        profile.permissions = validate_permissions(permissions)

    if password:
        validate_password(password, user=user)
        user.set_password(password)

    if is_active is not None:
        if not is_active:
            ensure_admin_capacity_preserved(
                proposed_is_active=False,
                target_user_id=user.pk,
            )
        user.is_active = is_active

    profile.save()
    user.save()
    return user


def seed_administrator_permissions():
    return list(ADMINISTRATOR_PERMISSION_CODES)


def create_staff_role(name, description, permissions):
    name = (name or "").strip()
    if not name:
        raise ValidationError("El nombre de la plantilla es obligatorio.")
    if StaffRole.objects.filter(name=name).exists():
        raise ValidationError("Ya existe una plantilla con ese nombre.")
    role = StaffRole(
        name=name,
        description=(description or "").strip(),
        permissions=validate_permissions(permissions),
    )
    role.save()
    return role


def update_staff_role(role, *, name=None, description=None, permissions=None):
    if name is not None:
        name = name.strip()
        if not name:
            raise ValidationError("El nombre de la plantilla es obligatorio.")
        if StaffRole.objects.filter(name=name).exclude(pk=role.pk).exists():
            raise ValidationError("Ya existe otra plantilla con ese nombre.")
        role.name = name
    if description is not None:
        role.description = description.strip()
    if permissions is not None:
        role.permissions = validate_permissions(permissions)
    role.save()
    return role


def delete_staff_role(role):
    if role.is_system:
        raise ValidationError("No se puede eliminar una plantilla del sistema.")
    role.delete()

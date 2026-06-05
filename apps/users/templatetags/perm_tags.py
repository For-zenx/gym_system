from django import template

from apps.clients.validation import display_client_phone, display_client_phone_feed
from apps.users.permissions import has_permission

register = template.Library()


@register.simple_tag(takes_context=True)
def user_can(context, permission_code):
    request = context.get("request")
    if request is None:
        return False
    return has_permission(request.user, permission_code)


@register.filter
def has_perm_code(user, permission_code):
    return has_permission(user, permission_code)


@register.simple_tag(takes_context=True)
def client_phone_display(context, telefono):
    can_view = "clients.view_phone" in context.get("user_permissions", set())
    return display_client_phone(telefono, can_view)


@register.simple_tag(takes_context=True)
def client_phone_display_feed(context, telefono):
    can_view = "clients.view_phone" in context.get("user_permissions", set())
    return display_client_phone_feed(telefono, can_view)

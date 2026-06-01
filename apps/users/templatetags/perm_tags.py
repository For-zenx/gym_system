from django import template

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

from django import template

from apps.billing.services import get_membership_feed_lines, get_membership_status_display

register = template.Library()


@register.filter
def membership_status_display(client):
    if not client:
        return "Sin plan activo"
    return get_membership_status_display(client)


@register.inclusion_tag("billing/includes/feed_membership_status.html")
def feed_membership_status(client):
    if not client:
        lines = [
            {
                "status": "empty",
                "title": "Sin plan activo",
                "primary": None,
                "secondary": None,
            }
        ]
    else:
        lines = get_membership_feed_lines(client)
    return {"lines": lines}

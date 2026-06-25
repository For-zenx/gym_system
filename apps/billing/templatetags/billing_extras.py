from django import template

from apps.billing.services import get_membership_feed_lines, get_membership_status_display
from apps.clients.services import get_guest_feed_lines

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
        kicker = "Membresía"
    else:
        if getattr(client, "is_guest", False):
            lines = get_guest_feed_lines(client)
            kicker = "Pase invitado"
        else:
            lines = get_membership_feed_lines(client)
            kicker = "Membresía"
    return {"lines": lines, "kicker": kicker}

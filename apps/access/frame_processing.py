import datetime

from apps.access import ai_engine
from apps.access.biometrics_audit import write_access_biometrics_log
from apps.access.services import (
    build_cooldown_denied_payload,
    build_tablet_access_payload,
    check_access_integrity,
    get_client_cooldown_remaining,
    log_cooldown_denial,
    log_unknown_access,
    pulse_turnstile_if_granted,
)


def _membership_data(client_obj):
    from django.utils import timezone

    active_mems = client_obj.active_memberships
    if not active_mems.exists():
        return None

    current_time = timezone.localtime().time()
    valid_now = [m for m in active_mems if m.is_valid_now(current_time)]
    mem = valid_now[0] if valid_now else active_mems.order_by("-fecha_fin").first()

    return {
        "plan_name": mem.plan.nombre,
        "fecha_fin": mem.fecha_fin.strftime("%d/%m/%Y"),
        "days_left": (mem.fecha_fin - datetime.date.today()).days,
    }


def _membership_lines(client):
    if client.is_guest:
        from apps.clients.services import get_guest_feed_lines

        return get_guest_feed_lines(client)
    from apps.billing.services import get_membership_feed_lines

    return get_membership_feed_lines(client)


def _dashboard_event(client, granted, detail, membership_lines, is_unknown=False):
    if is_unknown:
        return {
            "name": "No reconocido",
            "cedula": "",
            "codigo": "—",
            "telefono": "",
            "fecha_ingreso": "—",
            "photo_url": "",
            "granted": False,
            "detail": "No reconocido",
            "is_staff_person": False,
            "is_guest_person": False,
            "is_unknown": True,
            "membership_lines": [],
            "timestamp": datetime.datetime.now().strftime("%d/%m/%Y - %H:%M:%S"),
        }

    photo_url = client.foto_frente.url if client.foto_frente else ""
    return {
        "name": client.nombre,
        "cedula": client.cedula or "",
        "codigo": client.codigo_afiliado,
        "telefono": client.telefono,
        "fecha_ingreso": client.fecha_ingreso.strftime("%d/%m/%Y"),
        "photo_url": photo_url,
        "granted": granted,
        "detail": detail,
        "is_staff_person": client.is_staff_person,
        "is_guest_person": client.is_guest,
        "is_unknown": False,
        "membership_lines": membership_lines,
        "timestamp": datetime.datetime.now().strftime("%d/%m/%Y - %H:%M:%S"),
    }


def process_biometric_access_frame(base64_image: str, last_unknown_log_time):
    """
    Procesa un frame de acceso biométrico (sync).
    Retorna dict: tablet_response, dashboard_event (o None), should_log_unknown, match_result.
    """
    match_result = ai_engine.match_face(base64_image)
    client = match_result.client

    if client is None:
        write_access_biometrics_log(match_result, "DENIED", "denied_unknown")

        now = datetime.datetime.now()
        should_log_unknown = (
            last_unknown_log_time is None
            or (now - last_unknown_log_time).total_seconds() >= 10
        )
        if should_log_unknown:
            log_unknown_access()

        tablet_response = {
            "status": "DENIED",
            "variant": "denied_unknown",
            "name": "",
            "detail": "No reconocido",
        }
        dashboard_event = _dashboard_event(None, False, "No reconocido", [], is_unknown=True)
        return {
            "tablet_response": tablet_response,
            "dashboard_event": dashboard_event if should_log_unknown else None,
            "should_log_unknown": should_log_unknown,
            "match_result": match_result,
            "unknown_log_time": now if should_log_unknown else last_unknown_log_time,
        }

    remaining = get_client_cooldown_remaining(client)
    if remaining is not None:
        log_cooldown_denial(client, remaining)
        tablet_response = build_cooldown_denied_payload(client, remaining)
        write_access_biometrics_log(
            match_result,
            tablet_response.get("status", "DENIED"),
            tablet_response.get("variant", "denied_cooldown"),
        )
        membership_lines = _membership_lines(client)
        dashboard_event = _dashboard_event(
            client,
            False,
            tablet_response["detail"],
            membership_lines,
        )
        return {
            "tablet_response": tablet_response,
            "dashboard_event": dashboard_event,
            "should_log_unknown": False,
            "match_result": match_result,
            "unknown_log_time": last_unknown_log_time,
        }

    mem_data = _membership_data(client)
    granted, detail = check_access_integrity(client)
    pulse_turnstile_if_granted(granted)

    tablet_response = build_tablet_access_payload(client, granted, detail, mem_data)
    write_access_biometrics_log(
        match_result,
        tablet_response.get("status", "GRANTED" if granted else "DENIED"),
        tablet_response.get("variant", "granted" if granted else "denied_other"),
    )
    membership_lines = _membership_lines(client)
    dashboard_event = _dashboard_event(client, granted, detail, membership_lines)

    return {
        "tablet_response": tablet_response,
        "dashboard_event": dashboard_event,
        "should_log_unknown": False,
        "match_result": match_result,
        "unknown_log_time": last_unknown_log_time,
    }

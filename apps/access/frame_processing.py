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
)

PENDING_CONFIRM_TIMEOUT_SECONDS = 3.0


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


def _pending_expired(pending_client_id, pending_since, now):
    if pending_client_id is None or pending_since is None:
        return True
    return (now - pending_since).total_seconds() > PENDING_CONFIRM_TIMEOUT_SECONDS


def _finalize_matched_client(client, match_result, last_unknown_log_time, confirm_stage):
    remaining = get_client_cooldown_remaining(client)
    if remaining is not None:
        log_cooldown_denial(client, remaining)
        tablet_response = build_cooldown_denied_payload(client, remaining)
        write_access_biometrics_log(
            match_result,
            tablet_response.get("status", "DENIED"),
            tablet_response.get("variant", "denied_cooldown"),
            confirm_stage=confirm_stage,
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
            "pending_client_id": None,
            "pending_since": None,
        }

    mem_data = _membership_data(client)
    granted, detail = check_access_integrity(client)

    tablet_response = build_tablet_access_payload(client, granted, detail, mem_data)
    write_access_biometrics_log(
        match_result,
        tablet_response.get("status", "GRANTED" if granted else "DENIED"),
        tablet_response.get("variant", "granted" if granted else "denied_other"),
        confirm_stage=confirm_stage,
    )
    membership_lines = _membership_lines(client)
    dashboard_event = _dashboard_event(client, granted, detail, membership_lines)

    return {
        "tablet_response": tablet_response,
        "dashboard_event": dashboard_event,
        "should_log_unknown": False,
        "match_result": match_result,
        "unknown_log_time": last_unknown_log_time,
        "pending_client_id": None,
        "pending_since": None,
    }


def _unknown_result(match_result, last_unknown_log_time, confirm_stage="n/a"):
    now = datetime.datetime.now()
    write_access_biometrics_log(
        match_result,
        "DENIED",
        "denied_unknown",
        confirm_stage=confirm_stage,
    )
    should_log_unknown = (
        last_unknown_log_time is None
        or (now - last_unknown_log_time).total_seconds() >= 10
    )
    if should_log_unknown:
        log_unknown_access()

    return {
        "tablet_response": {
            "status": "DENIED",
            "variant": "denied_unknown",
            "name": "",
            "detail": "No reconocido",
        },
        "dashboard_event": (
            _dashboard_event(None, False, "No reconocido", [], is_unknown=True)
            if should_log_unknown
            else None
        ),
        "should_log_unknown": should_log_unknown,
        "match_result": match_result,
        "unknown_log_time": now if should_log_unknown else last_unknown_log_time,
        "pending_client_id": None,
        "pending_since": None,
    }


def process_biometric_access_frame(
    base64_image: str,
    last_unknown_log_time,
    pending_client_id=None,
    pending_since=None,
):
    """
    Procesa un frame de acceso biométrico (sync).
    Compatibilidad para tablets anteriores: requiere 2 MATCH de la misma persona.
    Durante pendiente, NO_MATCH/NO_FACE no cancelan (retry suave).
    """
    match_result = ai_engine.match_face(base64_image)
    client = match_result.client
    now = datetime.datetime.now()

    if _pending_expired(pending_client_id, pending_since, now):
        pending_client_id = None
        pending_since = None

    if client is None:
        if pending_client_id is not None:
            return _soft_pending_retry(
                match_result,
                last_unknown_log_time,
                pending_client_id,
                pending_since,
            )

        return _unknown_result(match_result, last_unknown_log_time)

    if pending_client_id is None or pending_client_id != client.pk:
        write_access_biometrics_log(
            match_result,
            "PENDING",
            "confirming",
            confirm_stage="pending",
        )
        tablet_response = {
            "status": "PENDING",
            "variant": "confirming",
            "name": "",
            "detail": "Siga frente a la cámara",
        }
        return {
            "tablet_response": tablet_response,
            "dashboard_event": None,
            "should_log_unknown": False,
            "match_result": match_result,
            "unknown_log_time": last_unknown_log_time,
            "pending_client_id": client.pk,
            "pending_since": now,
        }

    return _finalize_matched_client(
        client,
        match_result,
        last_unknown_log_time,
        confirm_stage="confirmed",
    )


def process_biometric_access_burst(images, last_unknown_log_time):
    """
    Identifica con el primer frame que haga MATCH y verifica 1:1 al candidato
    con los demás frames de la ráfaga hasta confirmar. Una sola respuesta final;
    nunca expone identidad provisional.
    """
    if not isinstance(images, (list, tuple)):
        match_result = ai_engine._empty_match_result(ai_engine.OUTCOME_INVALID_FRAME)
        return {
            "tablet_response": {
                "status": "ERROR",
                "reason": "Se requieren dos imágenes para verificar el acceso.",
            },
            "dashboard_event": None,
            "should_log_unknown": False,
            "match_result": match_result,
            "unknown_log_time": last_unknown_log_time,
            "pending_client_id": None,
            "pending_since": None,
        }

    frames = [image for image in images[:4] if isinstance(image, str) and image]
    if len(frames) < 2:
        match_result = ai_engine._empty_match_result(ai_engine.OUTCOME_INVALID_FRAME)
        return {
            "tablet_response": {
                "status": "ERROR",
                "reason": "Se requieren dos imágenes para verificar el acceso.",
            },
            "dashboard_event": None,
            "should_log_unknown": False,
            "match_result": match_result,
            "unknown_log_time": last_unknown_log_time,
            "pending_client_id": None,
            "pending_since": None,
        }

    identification = None
    identify_index = None
    candidate = None
    for index, frame in enumerate(frames):
        identification = ai_engine.match_face(frame)
        if identification.client is not None:
            identify_index = index
            candidate = identification.client
            break

    if candidate is None:
        return _unknown_result(
            identification,
            last_unknown_log_time,
            confirm_stage="burst_identify",
        )

    write_access_biometrics_log(
        identification,
        "PENDING",
        "burst_candidate",
        confirm_stage="burst_identify",
    )

    last_verification = None
    for index, frame in enumerate(frames):
        if index == identify_index:
            continue
        last_verification = ai_engine.verify_face(frame, candidate)
        if last_verification.client is not None:
            return _finalize_matched_client(
                candidate,
                last_verification,
                last_unknown_log_time,
                confirm_stage="burst_confirmed",
            )
        write_access_biometrics_log(
            last_verification,
            "PENDING",
            "burst_candidate",
            confirm_stage="burst_verify_retry",
        )

    return _unknown_result(
        last_verification or identification,
        last_unknown_log_time,
        confirm_stage="burst_rejected",
    )


def _soft_pending_retry(match_result, last_unknown_log_time, pending_client_id, pending_since):
    """Keep confirmation alive on a weak second frame (NO_MATCH / NO_FACE)."""
    write_access_biometrics_log(
        match_result,
        "PENDING",
        "confirming",
        confirm_stage="retry",
    )
    tablet_response = {
        "status": "PENDING",
        "variant": "confirming",
        "name": "",
        "detail": "Siga frente a la cámara",
    }
    return {
        "tablet_response": tablet_response,
        "dashboard_event": None,
        "should_log_unknown": False,
        "match_result": match_result,
        "unknown_log_time": last_unknown_log_time,
        "pending_client_id": pending_client_id,
        "pending_since": pending_since,
    }

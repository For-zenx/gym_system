import datetime
import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from apps.access.frame_processing import process_biometric_access_frame
from apps.access.tablet_ops_audit import write_tablet_ops_log

logger = logging.getLogger(__name__)

DASHBOARD_GROUP = "dashboard"
TABLET_ACCESS_GROUP = "tablet_access"
TABLET_ENROLLMENT_GROUP = "tablet_enrollment"
TABLET_COMBINED_GROUP = "tablet_enrolamiento_acceso"

TABLET_ROLE_ACCESS = "access"
TABLET_ROLE_ENROLLMENT = "enrollment"

OPS_ROLE_ACCESS = "acceso"
OPS_ROLE_ENROLLMENT = "enrolamiento"
OPS_ROLE_COMBINED = "combined"
OPS_ROLE_DASHBOARD = "dashboard"

ENROLLMENT_COMMAND_TYPES = (
    "ENROLLMENT_START",
    "ENROLLMENT_END",
    "ENROLLMENT_SKIP_TERMS",
    "ENROLLMENT_REQUIRE_TERMS",
)


# OPS_AUDIT
def _handle_ops_message(payload, default_role):
    write_tablet_ops_log(
        event=payload.get("event"),
        role=payload.get("role") or default_role,
        reason=payload.get("reason"),
        detail=payload.get("detail"),
    )


async def _send_access_frame_result(consumer, result):
    if result["dashboard_event"] is not None:
        event = {"type": "new_access_log"}
        event.update(result["dashboard_event"])
        await consumer.channel_layer.group_send(DASHBOARD_GROUP, event)

    await consumer.send(json.dumps(result["tablet_response"]))
    return result["unknown_log_time"]


async def _handle_access_frame(consumer, payload, last_unknown_log_time_attr):
    base64_image = payload.get("image", "")
    if not base64_image:
        await consumer.send(json.dumps({"status": "ERROR", "reason": "Campo 'image' vacío."}))
        return

    pending_client_id = getattr(consumer, "pending_client_id", None)
    pending_since = getattr(consumer, "pending_since", None)

    result = await database_sync_to_async(process_biometric_access_frame)(
        base64_image,
        getattr(type(consumer), last_unknown_log_time_attr),
        pending_client_id=pending_client_id,
        pending_since=pending_since,
    )
    consumer.pending_client_id = result.get("pending_client_id")
    consumer.pending_since = result.get("pending_since")
    setattr(
        type(consumer),
        last_unknown_log_time_attr,
        await _send_access_frame_result(consumer, result),
    )


class AccessTabletConsumer(AsyncWebsocketConsumer):
    last_unknown_log_time = None

    async def connect(self):
        await self.accept()
        self.pending_client_id = None
        self.pending_since = None
        await self.channel_layer.group_add(TABLET_ACCESS_GROUP, self.channel_name)
        logger.info("Tablet de acceso conectada. Canal: %s", self.channel_name)
        # OPS_AUDIT
        write_tablet_ops_log("connect", OPS_ROLE_ACCESS, "ws_accept", "—")
        await self._notify_dashboard(TABLET_ROLE_ACCESS, True)

    async def disconnect(self, code):
        await self.channel_layer.group_discard(TABLET_ACCESS_GROUP, self.channel_name)
        logger.info("Tablet de acceso desconectada. Canal: %s — Código: %s", self.channel_name, code)
        # OPS_AUDIT
        write_tablet_ops_log("disconnect", OPS_ROLE_ACCESS, "ws_close", "close_code={0}".format(code))
        await self._notify_dashboard(TABLET_ROLE_ACCESS, False)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Mensaje inválido recibido desde tablet de acceso: %s", text_data)
            await self.send(json.dumps({"status": "ERROR", "reason": "Formato de mensaje inválido. Se esperaba JSON."}))
            return

        msg_type = payload.get("type")
        if msg_type == "PING":
            await self.send(json.dumps({"type": "PONG"}))
        elif msg_type == "FRAME":
            await self._handle_frame(payload)
        elif msg_type == "OPS":
            # OPS_AUDIT
            _handle_ops_message(payload, OPS_ROLE_ACCESS)
        else:
            logger.warning("Tipo de mensaje desconocido en tablet de acceso: %s", msg_type)
            await self.send(json.dumps({"status": "ERROR", "reason": f"Tipo de mensaje no reconocido: '{msg_type}'"}))

    async def _handle_frame(self, payload):
        await _handle_access_frame(self, payload, "last_unknown_log_time")

    async def tablet_status_request(self, event):
        await self._notify_dashboard(TABLET_ROLE_ACCESS, True)

    async def tablet_reload(self, event):
        await self.send(json.dumps({"type": "TABLET_RELOAD"}))

    async def _notify_dashboard(self, role, online):
        await self.channel_layer.group_send(
            DASHBOARD_GROUP,
            {"type": "tablet_status", "role": role, "online": online},
        )


class EnrollmentTabletConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        await self.accept()
        await self.channel_layer.group_add(TABLET_ENROLLMENT_GROUP, self.channel_name)
        logger.info("Tablet de enrolamiento conectada. Canal: %s", self.channel_name)
        # OPS_AUDIT
        write_tablet_ops_log("connect", OPS_ROLE_ENROLLMENT, "ws_accept", "—")
        await self._notify_dashboard(TABLET_ROLE_ENROLLMENT, True)

    async def disconnect(self, code):
        await self.channel_layer.group_discard(TABLET_ENROLLMENT_GROUP, self.channel_name)
        logger.info("Tablet de enrolamiento desconectada. Canal: %s — Código: %s", self.channel_name, code)
        # OPS_AUDIT
        write_tablet_ops_log("disconnect", OPS_ROLE_ENROLLMENT, "ws_close", "close_code={0}".format(code))
        await self._notify_dashboard(TABLET_ROLE_ENROLLMENT, False)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Mensaje inválido recibido desde tablet de enrolamiento: %s", text_data)
            await self.send(json.dumps({"status": "ERROR", "reason": "Formato de mensaje inválido. Se esperaba JSON."}))
            return

        msg_type = payload.get("type")
        if msg_type == "PING":
            await self.send(json.dumps({"type": "PONG"}))
        elif msg_type == "ENROLLMENT_PHOTO":
            await self.channel_layer.group_send(
                DASHBOARD_GROUP,
                {
                    "type": "enrollment_photo_forward",
                    "photoType": payload.get("photoType"),
                    "image": payload.get("image"),
                },
            )
        elif msg_type == "OPS":
            # OPS_AUDIT
            _handle_ops_message(payload, OPS_ROLE_ENROLLMENT)
        else:
            logger.warning("Tipo de mensaje desconocido en tablet de enrolamiento: %s", msg_type)
            await self.send(json.dumps({"status": "ERROR", "reason": f"Tipo de mensaje no reconocido: '{msg_type}'"}))

    async def enrollment_command(self, event):
        await self.send(json.dumps(event.get("data", {})))

    async def tablet_status_request(self, event):
        await self._notify_dashboard(TABLET_ROLE_ENROLLMENT, True)

    async def tablet_reload(self, event):
        await self.send(json.dumps({"type": "TABLET_RELOAD"}))

    async def _notify_dashboard(self, role, online):
        await self.channel_layer.group_send(
            DASHBOARD_GROUP,
            {"type": "tablet_status", "role": role, "online": online},
        )


class CombinedTabletConsumer(AsyncWebsocketConsumer):
    """
    Tablet única: acceso + enrolamiento en un dispositivo.
    Reporta ambos roles online al dashboard; recibe ENROLLMENT_* y FRAME.
    """

    last_unknown_log_time = None

    async def connect(self):
        await self.accept()
        self.pending_client_id = None
        self.pending_since = None
        await self.channel_layer.group_add(TABLET_COMBINED_GROUP, self.channel_name)
        logger.info("Tablet enrolamiento_acceso conectada. Canal: %s", self.channel_name)
        # OPS_AUDIT
        write_tablet_ops_log("connect", OPS_ROLE_COMBINED, "ws_accept", "—")
        await self._notify_dashboard(TABLET_ROLE_ACCESS, True)
        await self._notify_dashboard(TABLET_ROLE_ENROLLMENT, True)

    async def disconnect(self, code):
        await self.channel_layer.group_discard(TABLET_COMBINED_GROUP, self.channel_name)
        logger.info(
            "Tablet enrolamiento_acceso desconectada. Canal: %s — Código: %s",
            self.channel_name,
            code,
        )
        # OPS_AUDIT
        write_tablet_ops_log("disconnect", OPS_ROLE_COMBINED, "ws_close", "close_code={0}".format(code))
        await self._notify_dashboard(TABLET_ROLE_ACCESS, False)
        await self._notify_dashboard(TABLET_ROLE_ENROLLMENT, False)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "Mensaje inválido recibido desde tablet enrolamiento_acceso: %s",
                text_data,
            )
            await self.send(
                json.dumps(
                    {
                        "status": "ERROR",
                        "reason": "Formato de mensaje inválido. Se esperaba JSON.",
                    }
                )
            )
            return

        msg_type = payload.get("type")
        if msg_type == "PING":
            await self.send(json.dumps({"type": "PONG"}))
        elif msg_type == "FRAME":
            await self._handle_frame(payload)
        elif msg_type == "ENROLLMENT_PHOTO":
            await self.channel_layer.group_send(
                DASHBOARD_GROUP,
                {
                    "type": "enrollment_photo_forward",
                    "photoType": payload.get("photoType"),
                    "image": payload.get("image"),
                },
            )
        elif msg_type == "OPS":
            # OPS_AUDIT
            _handle_ops_message(payload, OPS_ROLE_COMBINED)
        else:
            logger.warning(
                "Tipo de mensaje desconocido en tablet enrolamiento_acceso: %s",
                msg_type,
            )
            await self.send(
                json.dumps(
                    {
                        "status": "ERROR",
                        "reason": "Tipo de mensaje no reconocido: '{0}'".format(msg_type),
                    }
                )
            )

    async def _handle_frame(self, payload):
        await _handle_access_frame(self, payload, "last_unknown_log_time")

    async def enrollment_command(self, event):
        await self.send(json.dumps(event.get("data", {})))

    async def tablet_status_request(self, event):
        await self._notify_dashboard(TABLET_ROLE_ACCESS, True)
        await self._notify_dashboard(TABLET_ROLE_ENROLLMENT, True)

    async def tablet_reload(self, event):
        await self.send(json.dumps({"type": "TABLET_RELOAD"}))

    async def _notify_dashboard(self, role, online):
        await self.channel_layer.group_send(
            DASHBOARD_GROUP,
            {"type": "tablet_status", "role": role, "online": online},
        )


class DashboardConsumer(AsyncWebsocketConsumer):
    """WebSocket pasivo para la interfaz administrativa (PC)."""
    
    _is_enrollment_mode = False

    async def connect(self):
        await self.accept()
        await self.channel_layer.group_add(DASHBOARD_GROUP, self.channel_name)
        logger.info("Dashboard (PC) conectado. Canal: %s", self.channel_name)
        # OPS_AUDIT
        write_tablet_ops_log("connect", OPS_ROLE_DASHBOARD, "ws_accept", "—")
        await self.channel_layer.group_send(TABLET_ACCESS_GROUP, {"type": "tablet_status_request"})
        await self.channel_layer.group_send(TABLET_ENROLLMENT_GROUP, {"type": "tablet_status_request"})
        await self.channel_layer.group_send(TABLET_COMBINED_GROUP, {"type": "tablet_status_request"})
        
        if DashboardConsumer._is_enrollment_mode:
            await self.send(json.dumps({
                "type": "TABLET_MODE_CHANGED",
                "mode": "enrollment"
            }))

    async def disconnect(self, code):
        await self.channel_layer.group_discard(DASHBOARD_GROUP, self.channel_name)
        logger.info("Dashboard (PC) desconectado. Canal: %s", self.channel_name)
        # OPS_AUDIT
        write_tablet_ops_log("disconnect", OPS_ROLE_DASHBOARD, "ws_close", "close_code={0}".format(code))

    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.error("Error procesando mensaje desde Dashboard: %s", exc)
            return

        msg_type = payload.get("type")
        if msg_type == "TABLET_RELOAD":
            # OPS_AUDIT
            write_tablet_ops_log("tablet_reload", OPS_ROLE_DASHBOARD, "dashboard_forced", "—")
            reload_event = {"type": "tablet_reload"}
            await self.channel_layer.group_send(TABLET_ACCESS_GROUP, reload_event)
            await self.channel_layer.group_send(TABLET_ENROLLMENT_GROUP, reload_event)
            await self.channel_layer.group_send(TABLET_COMBINED_GROUP, reload_event)
        elif msg_type in ENROLLMENT_COMMAND_TYPES:
            command = {"type": "enrollment_command", "data": payload}
            await self.channel_layer.group_send(TABLET_ENROLLMENT_GROUP, command)
            await self.channel_layer.group_send(TABLET_COMBINED_GROUP, command)

            if msg_type in ("ENROLLMENT_START", "ENROLLMENT_END"):
                mode = "enrollment" if msg_type == "ENROLLMENT_START" else "access"
                DashboardConsumer._is_enrollment_mode = (mode == "enrollment")
                await self.channel_layer.group_send(
                    DASHBOARD_GROUP,
                    {
                        "type": "tablet_mode_changed",
                        "mode": mode
                    }
                )

    async def tablet_mode_changed(self, event):
        await self.send(json.dumps({
            "type": "TABLET_MODE_CHANGED",
            "mode": event.get("mode"),
        }))

    async def tablet_status(self, event):
        await self.send(json.dumps({
            "type": "tablet_status",
            "role": event.get("role"),
            "online": event.get("online", False),
        }))

    async def enrollment_photo_forward(self, event):
        await self.send(json.dumps({
            "type": "ENROLLMENT_PHOTO",
            "photoType": event.get("photoType"),
            "image": event.get("image"),
        }))

    async def new_access_log(self, event):
        await self.send(json.dumps({
            "type": "NEW_ACCESS_LOG",
            "name": event.get("name"),
            "cedula": event.get("cedula"),
            "codigo": event.get("codigo"),
            "telefono": event.get("telefono"),
            "fecha_ingreso": event.get("fecha_ingreso"),
            "photo_url": event.get("photo_url"),
            "granted": event.get("granted"),
            "detail": event.get("detail"),
            "is_staff_person": event.get("is_staff_person", False),
            "is_guest_person": event.get("is_guest_person", False),
            "membership_lines": event.get("membership_lines", []),
            "timestamp": event.get("timestamp"),
        }))

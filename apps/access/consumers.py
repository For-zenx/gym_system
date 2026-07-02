import datetime
import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from apps.access import ai_engine
from apps.access.services import (
    build_tablet_access_payload,
    check_access_integrity,
    log_unknown_access,
    pulse_turnstile_if_granted,
)

logger = logging.getLogger(__name__)

DASHBOARD_GROUP = "dashboard"
TABLET_ACCESS_GROUP = "tablet_access"
TABLET_ENROLLMENT_GROUP = "tablet_enrollment"

TABLET_ROLE_ACCESS = "access"
TABLET_ROLE_ENROLLMENT = "enrollment"


class AccessTabletConsumer(AsyncWebsocketConsumer):
    last_unknown_log_time = None

    async def connect(self):
        await self.accept()
        await self.channel_layer.group_add(TABLET_ACCESS_GROUP, self.channel_name)
        logger.info("Tablet de acceso conectada. Canal: %s", self.channel_name)
        await self._notify_dashboard(TABLET_ROLE_ACCESS, True)

    async def disconnect(self, code):
        await self.channel_layer.group_discard(TABLET_ACCESS_GROUP, self.channel_name)
        logger.info("Tablet de acceso desconectada. Canal: %s — Código: %s", self.channel_name, code)
        await self._notify_dashboard(TABLET_ROLE_ACCESS, False)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Mensaje inválido recibido desde tablet de acceso: %s", text_data)
            await self.send(json.dumps({"status": "ERROR", "reason": "Formato de mensaje inválido. Se esperaba JSON."}))
            return

        if payload.get("type") == "FRAME":
            await self._handle_frame(payload)
        else:
            message_type = payload.get("type")
            logger.warning("Tipo de mensaje desconocido en tablet de acceso: %s", message_type)
            await self.send(json.dumps({"status": "ERROR", "reason": f"Tipo de mensaje no reconocido: '{message_type}'"}))

    async def _handle_frame(self, payload):
        base64_image = payload.get("image", "")
        if not base64_image:
            await self.send(json.dumps({"status": "ERROR", "reason": "Campo 'image' vacío."}))
            return

        client = await database_sync_to_async(ai_engine.recognize_face)(base64_image)

        if client is None:
            now = datetime.datetime.now()
            should_log = False
            if (
                AccessTabletConsumer.last_unknown_log_time is None
                or (now - AccessTabletConsumer.last_unknown_log_time).total_seconds()
                >= 10
            ):
                AccessTabletConsumer.last_unknown_log_time = now
                should_log = True

            if should_log:
                await database_sync_to_async(log_unknown_access)()
                await self.channel_layer.group_send(
                    DASHBOARD_GROUP,
                    {
                        "type": "new_access_log",
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
                        "timestamp": now.strftime("%d/%m/%Y - %H:%M:%S"),
                    },
                )

            await self.send(
                json.dumps(
                    {
                        "status": "DENIED",
                        "variant": "denied_unknown",
                        "name": "",
                        "detail": "No reconocido",
                    }
                )
            )
            return

        def get_membership_data(client_obj):
            from django.utils import timezone

            active_mems = client_obj.active_memberships
            if not active_mems.exists():
                return None

            current_time = timezone.localtime().time()
            valid_now = [m for m in active_mems if m.is_valid_now(current_time)]
            mem = valid_now[0] if valid_now else active_mems.order_by('-fecha_fin').first()

            return {
                "plan_name": mem.plan.nombre,
                "fecha_fin": mem.fecha_fin.strftime('%d/%m/%Y'),
                "days_left": (mem.fecha_fin - datetime.date.today()).days,
            }

        mem_data = await database_sync_to_async(get_membership_data)(client)
        granted, detail = await database_sync_to_async(check_access_integrity)(client)

        await database_sync_to_async(pulse_turnstile_if_granted)(granted)

        tablet_payload = await database_sync_to_async(build_tablet_access_payload)(
            client, granted, detail, mem_data
        )
        await self.send(json.dumps(tablet_payload))

        photo_url = client.foto_frente.url if client.foto_frente else ""
        if client.is_guest:
            from apps.clients.services import get_guest_feed_lines

            membership_lines = await database_sync_to_async(get_guest_feed_lines)(client)
        else:
            from apps.billing.services import get_membership_feed_lines

            membership_lines = await database_sync_to_async(get_membership_feed_lines)(client)

        await self.channel_layer.group_send(
            DASHBOARD_GROUP,
            {
                "type": "new_access_log",
                "name": client.nombre,
                "cedula": client.cedula or "",
                "codigo": client.codigo_afiliado,
                "telefono": client.telefono,
                "fecha_ingreso": client.fecha_ingreso.strftime('%d/%m/%Y'),
                "photo_url": photo_url,
                "granted": granted,
                "detail": detail,
                "is_staff_person": client.is_staff_person,
                "is_guest_person": client.is_guest,
                "membership_lines": membership_lines,
                "timestamp": datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S'),
            },
        )

    async def tablet_status_request(self, event):
        await self._notify_dashboard(TABLET_ROLE_ACCESS, True)

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
        await self._notify_dashboard(TABLET_ROLE_ENROLLMENT, True)

    async def disconnect(self, code):
        await self.channel_layer.group_discard(TABLET_ENROLLMENT_GROUP, self.channel_name)
        logger.info("Tablet de enrolamiento desconectada. Canal: %s — Código: %s", self.channel_name, code)
        await self._notify_dashboard(TABLET_ROLE_ENROLLMENT, False)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Mensaje inválido recibido desde tablet de enrolamiento: %s", text_data)
            await self.send(json.dumps({"status": "ERROR", "reason": "Formato de mensaje inválido. Se esperaba JSON."}))
            return

        if payload.get("type") == "ENROLLMENT_PHOTO":
            await self.channel_layer.group_send(
                DASHBOARD_GROUP,
                {
                    "type": "enrollment_photo_forward",
                    "photoType": payload.get("photoType"),
                    "image": payload.get("image"),
                },
            )
        elif payload.get("type") == "ENROLLMENT_TERMS_ACCEPTED":
            await self.channel_layer.group_send(
                DASHBOARD_GROUP,
                {"type": "enrollment_terms_forward"},
            )
        else:
            message_type = payload.get("type")
            logger.warning("Tipo de mensaje desconocido en tablet de enrolamiento: %s", message_type)
            await self.send(json.dumps({"status": "ERROR", "reason": f"Tipo de mensaje no reconocido: '{message_type}'"}))

    async def enrollment_command(self, event):
        await self.send(json.dumps(event.get("data", {})))

    async def tablet_status_request(self, event):
        await self._notify_dashboard(TABLET_ROLE_ENROLLMENT, True)

    async def _notify_dashboard(self, role, online):
        await self.channel_layer.group_send(
            DASHBOARD_GROUP,
            {"type": "tablet_status", "role": role, "online": online},
        )


class DashboardConsumer(AsyncWebsocketConsumer):
    """WebSocket pasivo para la interfaz administrativa (PC)."""

    async def connect(self):
        await self.accept()
        await self.channel_layer.group_add(DASHBOARD_GROUP, self.channel_name)
        logger.info("Dashboard (PC) conectado. Canal: %s", self.channel_name)
        await self.channel_layer.group_send(TABLET_ACCESS_GROUP, {"type": "tablet_status_request"})
        await self.channel_layer.group_send(TABLET_ENROLLMENT_GROUP, {"type": "tablet_status_request"})

    async def disconnect(self, code):
        await self.channel_layer.group_discard(DASHBOARD_GROUP, self.channel_name)
        logger.info("Dashboard (PC) desconectado. Canal: %s", self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.error("Error procesando mensaje desde Dashboard: %s", exc)
            return

        msg_type = payload.get("type")
        if msg_type in ("ENROLLMENT_START", "ENROLLMENT_END", "ENROLLMENT_SKIP_TERMS", "ENROLLMENT_REQUIRE_TERMS"):
            await self.channel_layer.group_send(
                TABLET_ENROLLMENT_GROUP,
                {"type": "enrollment_command", "data": payload},
            )

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

    async def enrollment_terms_forward(self, event):
        await self.send(json.dumps({
            "type": "ENROLLMENT_TERMS_ACCEPTED",
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

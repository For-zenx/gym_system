import base64
import datetime
import json
import logging
from pathlib import Path

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from apps.access import ai_engine
from apps.access.services import check_access_integrity

logger = logging.getLogger(__name__)

DASHBOARD_GROUP = "dashboard"


class TabletConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        await self.accept()
        await self.channel_layer.group_add(DASHBOARD_GROUP, self.channel_name)
        logger.info("Tablet conectada. Canal: %s", self.channel_name)
        await self.channel_layer.group_send(DASHBOARD_GROUP, {"type": "tablet_status", "online": True})

    async def disconnect(self, code):
        await self.channel_layer.group_discard(DASHBOARD_GROUP, self.channel_name)
        logger.info("Tablet desconectada. Canal: %s — Código: %s", self.channel_name, code)
        await self.channel_layer.group_send(DASHBOARD_GROUP, {"type": "tablet_status", "online": False})

    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Mensaje inválido recibido desde la tablet: %s", text_data)
            await self.send(json.dumps({"status": "ERROR", "reason": "Formato de mensaje inválido. Se esperaba JSON."}))
            return

        message_type = payload.get("type")

        if message_type == "FRAME":
            await self._handle_frame(payload)
        elif message_type == "ENROLLMENT_PHOTO":
            await self._handle_enrollment_photo(payload)
        else:
            logger.warning("Tipo de mensaje desconocido recibido: %s", message_type)
            await self.send(json.dumps({"status": "ERROR", "reason": f"Tipo de mensaje no reconocido: '{message_type}'"}))

    async def _handle_frame(self, payload: dict):
        base64_image = payload.get("image", "")
        if not base64_image:
            await self.send(json.dumps({"status": "ERROR", "reason": "Campo 'image' vacío."}))
            return

        client = await database_sync_to_async(ai_engine.recognize_face)(base64_image)

        if client is None:
            await self.send(json.dumps({"status": "DENIED", "reason": "No reconocido"}))
            return

        granted, detail = await database_sync_to_async(check_access_integrity)(client)

        if granted:
            membership = await database_sync_to_async(lambda: getattr(client, "membership", None))()
            days_left = (membership.fecha_fin - datetime.date.today()).days if membership else 0
            await self.send(json.dumps({"status": "GRANTED", "name": client.nombre, "days_left": max(days_left, 0)}))
        else:
            await self.send(json.dumps({"status": "DENIED", "name": client.nombre, "reason": detail}))

    async def _handle_enrollment_photo(self, payload: dict):
        client_id = payload.get("client_id")
        step = payload.get("step")
        base64_image = payload.get("image", "")

        if not all([client_id, step, base64_image]):
            await self.send(json.dumps({"status": "ERROR", "reason": "Faltan campos requeridos: client_id, step, image."}))
            return

        step_to_field = {1: "foto_frente", 2: "foto_perfil_izq", 3: "foto_perfil_der"}
        field_name = step_to_field.get(step)
        if not field_name:
            await self.send(json.dumps({"status": "ERROR", "reason": f"Step inválido: {step}. Debe ser 1, 2 o 3."}))
            return

        try:
            img_data = base64_image.split(",", 1)[-1] if "," in base64_image else base64_image
            image_bytes = base64.b64decode(img_data)
        except Exception as exc:
            logger.error("Error al decodificar foto de enrolamiento paso %s: %s", step, exc)
            await self.send(json.dumps({"status": "ERROR", "reason": "Imagen Base64 inválida."}))
            return

        enrollment_dir = Path(settings.MEDIA_ROOT) / "clients" / "enrollment"
        enrollment_dir.mkdir(parents=True, exist_ok=True)
        filename = f"client_{client_id}_step_{step}.jpg"
        (enrollment_dir / filename).write_bytes(image_bytes)

        relative_path = Path("clients") / "enrollment" / filename

        def save_photo_field():
            from apps.clients.models import Client
            client = Client.objects.get(pk=client_id)
            setattr(client, field_name, str(relative_path))
            client.save(update_fields=[field_name])
            return client

        try:
            client = await database_sync_to_async(save_photo_field)()
        except Exception as exc:
            logger.error("Error al guardar campo %s para cliente %s: %s", field_name, client_id, exc)
            await self.send(json.dumps({"status": "ERROR", "reason": "Error al guardar la foto en la base de datos."}))
            return

        logger.info("Foto de enrolamiento guardada: cliente=%s, paso=%s", client_id, step)

        if step == 3:
            try:
                await database_sync_to_async(ai_engine.update_client_embeddings)(client)
                await self.send(json.dumps({"status": "ENROLLMENT_COMPLETE", "client_id": client_id, "name": client.nombre}))
            except (ValueError, FileNotFoundError) as exc:
                logger.error("Error al generar embedding para cliente %s: %s", client_id, exc)
                await self.send(json.dumps({"status": "ERROR", "reason": f"Error al procesar el enrolamiento: {exc}"}))
        else:
            await self.send(json.dumps({"status": "PHOTO_RECEIVED", "step": step, "next_step": step + 1}))

    async def tablet_status(self, event):
        # Consumido por el dashboard via group_send; la tablet no necesita respuesta.
        pass

    async def dashboard_message(self, event):
        data = event.get("data", {})
        if data.get("type") == "TABLET_STATUS_REQUEST":
            await self.channel_layer.group_send(DASHBOARD_GROUP, {"type": "tablet_status", "online": True})
        else:
            await self.send(json.dumps(data))


class DashboardConsumer(AsyncWebsocketConsumer):
    """
    WebSocket pasivo para la interfaz administrativa (PC).
    """
    async def connect(self):
        await self.accept()
        await self.channel_layer.group_add(DASHBOARD_GROUP, self.channel_name)
        logger.info("Dashboard (PC) conectado. Canal: %s", self.channel_name)
        
        # Al conectarse, preguntamos al grupo si hay alguna tablet conectada
        await self.channel_layer.group_send(
            DASHBOARD_GROUP, 
            {"type": "dashboard_message", "data": {"type": "TABLET_STATUS_REQUEST"}}
        )

    async def disconnect(self, code):
        await self.channel_layer.group_discard(DASHBOARD_GROUP, self.channel_name)
        logger.info("Dashboard (PC) desconectado. Canal: %s", self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data)
            await self.channel_layer.group_send(
                DASHBOARD_GROUP,
                {"type": "dashboard_message", "data": payload}
            )
        except Exception as e:
            logger.error("Error procesando mensaje desde Dashboard: %s", e)

    async def tablet_status(self, event):
        # Cuando la tablet cambia de estado, notificamos a la PC
        await self.send(json.dumps({
            "type": "tablet_status",
            "online": event.get("online", False)
        }))

    async def dashboard_message(self, event):
        # Este consumidor también está en el grupo 'dashboard', por lo que recibe los
        # comandos (ej. ENROLLMENT_START). Como estos comandos son para la tablet,
        # simplemente los ignoramos en la PC para evitar el error "No handler".
        pass


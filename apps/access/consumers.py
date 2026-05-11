import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)

# Nombre del grupo de canales que representa el dashboard administrativo.
# Todos los mensajes de estado de la tablet se publican en este grupo.
DASHBOARD_GROUP = "dashboard"


class TabletConsumer(AsyncWebsocketConsumer):
    """
    Consumidor WebSocket para la tablet de acceso.
    """

    async def connect(self):
        await self.accept()
        await self.channel_layer.group_add(DASHBOARD_GROUP, self.channel_name)
        logger.info("Tablet conectada. Canal: %s", self.channel_name)

        # Notificar al dashboard que la tablet está en línea.
        await self.channel_layer.group_send(
            DASHBOARD_GROUP,
            {"type": "tablet_status", "online": True},
        )

    async def disconnect(self, code):
        await self.channel_layer.group_discard(DASHBOARD_GROUP, self.channel_name)
        logger.info("Tablet desconectada. Canal: %s — Código: %s", self.channel_name, code)

        # Notificar al dashboard que la tablet está fuera de línea.
        await self.channel_layer.group_send(
            DASHBOARD_GROUP,
            {"type": "tablet_status", "online": False},
        )

    async def receive(self, text_data=None, bytes_data=None):
        """
        Punto de entrada para todos los mensajes enviados por la tablet.
        """
        try:
            payload = json.loads(text_data)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Mensaje inválido recibido desde la tablet: %s", text_data)
            await self.send(json.dumps({
                "status": "ERROR",
                "reason": "Formato de mensaje inválido. Se esperaba JSON.",
            }))
            return

        message_type = payload.get("type")

        if message_type == "FRAME":
            await self._handle_frame(payload)
        elif message_type == "ENROLLMENT_PHOTO":
            await self._handle_enrollment_photo(payload)
        else:
            logger.warning("Tipo de mensaje desconocido recibido: %s", message_type)
            await self.send(json.dumps({
                "status": "ERROR",
                "reason": f"Tipo de mensaje no reconocido: '{message_type}'",
            }))

    # -------------------------------------------------------------------------
    # Handlers de mensajes entrantes
    # -------------------------------------------------------------------------

    async def _handle_frame(self, payload: dict):
        """
        Recibe un frame de la tablet para reconocimiento facial.
        """
        logger.debug("Frame recibido para reconocimiento (pendiente motor IA).")
        await self.send(json.dumps({
            "status": "PENDING_AI_MODULE",
            "detail": "Motor biométrico no disponible aún (Cap 6-B).",
        }))

    async def _handle_enrollment_photo(self, payload: dict):
        """
        Recibe una foto de enrolamiento desde la tablet.
        PLACEHOLDER: Se implementará completamente en Cap 6-B.
        """
        step = payload.get("step")
        logger.debug("Foto de enrolamiento paso %s recibida (pendiente motor IA).", step)
        await self.send(json.dumps({
            "status": "PENDING_AI_MODULE",
            "detail": "Motor biométrico no disponible aún (Cap 6-B).",
        }))

    # -------------------------------------------------------------------------
    # Handlers de mensajes del grupo (dashboard → tablet)
    # -------------------------------------------------------------------------

    async def tablet_status(self, event):
        """
        Reenvía el evento de estado de conexión al cliente WebSocket.
        Usado internamente por group_send; la tablet no necesita procesar esto,
        pero el dashboard sí lo recibe para actualizar su indicador de estado.
        """
        pass

    async def dashboard_message(self, event):
        """
        Reenvía un comando genérico del dashboard a la tablet.
        Ejemplo de uso: activar 'Modo Enrolamiento' desde la PC.
        El dashboard publica en el grupo y la tablet recibe aquí.
        """
        await self.send(json.dumps(event.get("data", {})))

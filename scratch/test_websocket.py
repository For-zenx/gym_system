"""
Simula el comportamiento de la tablet usando channels.testing.WebsocketCommunicator.
"""

import json
import pytest
from channels.testing import WebsocketCommunicator

from config.asgi import application


@pytest.mark.asyncio
async def test_tablet_connects_and_is_accepted():
    """La tablet se conecta al WebSocket y el servidor acepta la conexión."""
    communicator = WebsocketCommunicator(application, "/ws/tablet/")
    connected, subprotocol = await communicator.connect()

    assert connected, "El servidor debe aceptar la conexión WebSocket de la tablet."

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_tablet_disconnects_without_error():
    """La tablet se desconecta y el servidor no lanza ninguna excepción."""
    communicator = WebsocketCommunicator(application, "/ws/tablet/")
    await communicator.connect()
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_frame_message_returns_valid_json():
    """
    La tablet envía un mensaje de tipo FRAME.
    """
    communicator = WebsocketCommunicator(application, "/ws/tablet/")
    await communicator.connect()

    payload = json.dumps({"type": "FRAME", "image": "data:image/jpeg;base64,/9j/PLACEHOLDER=="})
    await communicator.send_to(text_data=payload)

    response = await communicator.receive_from()
    data = json.loads(response)

    assert "status" in data, "La respuesta debe tener el campo 'status'."
    # En Cap 6-A el status es el placeholder; en Cap 6-B será GRANTED o DENIED.
    assert data["status"] in ("GRANTED", "DENIED", "PENDING_AI_MODULE"), (
        f"Status inesperado: {data['status']}"
    )

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_enrollment_photo_message_returns_valid_json():
    """
    La tablet envía una foto de enrolamiento (paso 1).
    El servidor debe responder con un JSON válido.
    """
    communicator = WebsocketCommunicator(application, "/ws/tablet/")
    await communicator.connect()

    payload = json.dumps({
        "type": "ENROLLMENT_PHOTO",
        "client_id": 1,
        "step": 1,
        "image": "data:image/jpeg;base64,/9j/PLACEHOLDER==",
    })
    await communicator.send_to(text_data=payload)

    response = await communicator.receive_from()
    data = json.loads(response)

    assert "status" in data, "La respuesta debe tener el campo 'status'."

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_invalid_json_returns_error_status():
    """
    La tablet envía datos que no son JSON válido.
    El servidor debe responder con status ERROR en lugar de crashear.
    """
    communicator = WebsocketCommunicator(application, "/ws/tablet/")
    await communicator.connect()

    await communicator.send_to(text_data="esto no es json {{{")

    response = await communicator.receive_from()
    data = json.loads(response)

    assert data["status"] == "ERROR", (
        "Un mensaje inválido debe retornar status ERROR, no crashear el servidor."
    )

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_unknown_message_type_returns_error_status():
    """
    La tablet envía un tipo de mensaje desconocido.
    El servidor debe responder con status ERROR en lugar de silenciarlo.
    """
    communicator = WebsocketCommunicator(application, "/ws/tablet/")
    await communicator.connect()

    payload = json.dumps({"type": "TIPO_INEXISTENTE", "data": "algo"})
    await communicator.send_to(text_data=payload)

    response = await communicator.receive_from()
    data = json.loads(response)

    assert data["status"] == "ERROR", (
        "Un tipo de mensaje desconocido debe retornar status ERROR."
    )

    await communicator.disconnect()

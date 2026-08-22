import pytest
from channels.testing import WebsocketCommunicator

from config.asgi import application

from tests.access.conftest import (
    WS_DASHBOARD,
    WS_TABLET_ENROLLMENT,
    receive_json_skipping_status,
)
from tests.core.conftest import FAKE_PHOTO_B64


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_tablet_enrollment_ws__connects():
    communicator = WebsocketCommunicator(application, WS_TABLET_ENROLLMENT)
    connected, _ = await communicator.connect()
    assert connected
    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_tablet_enrollment_ws__photo_reaches_dashboard():
    tablet = WebsocketCommunicator(application, WS_TABLET_ENROLLMENT)
    dashboard = WebsocketCommunicator(application, WS_DASHBOARD)

    await tablet.connect()
    await dashboard.connect()

    await tablet.send_json_to(
        {
            "type": "ENROLLMENT_PHOTO",
            "photoType": "frente",
            "image": FAKE_PHOTO_B64,
        }
    )

    message = await receive_json_skipping_status(dashboard, "ENROLLMENT_PHOTO")
    assert message["photoType"] == "frente"
    assert message["image"] == FAKE_PHOTO_B64

    await tablet.disconnect()
    await dashboard.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_tablet_enrollment_ws__unknown_type_returns_error():
    tablet = WebsocketCommunicator(application, WS_TABLET_ENROLLMENT)
    await tablet.connect()

    await tablet.send_json_to({"type": "ENROLLMENT_TERMS_ACCEPTED"})
    response = await tablet.receive_json_from()

    assert response["status"] == "ERROR"
    assert "ENROLLMENT_TERMS_ACCEPTED" in response["reason"]

    await tablet.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_tablet_enrollment_ws__dashboard_start_command_reaches_tablet():
    tablet = WebsocketCommunicator(application, WS_TABLET_ENROLLMENT)
    dashboard = WebsocketCommunicator(application, WS_DASHBOARD)

    await tablet.connect()
    await dashboard.connect()

    await dashboard.send_json_to({"type": "ENROLLMENT_START", "sessionId": "test-1"})

    message = await receive_json_skipping_status(tablet, "ENROLLMENT_START")
    assert message["sessionId"] == "test-1"

    await tablet.disconnect()
    await dashboard.disconnect()

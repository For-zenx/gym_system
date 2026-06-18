import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator

from apps.access.hardware import TurnstilePulseResult
from apps.access.models import AccessLog
from config.asgi import application

from tests.access.conftest import WS_TABLET_ACCESS
from tests.core.conftest import FAKE_PHOTO_B64


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_tablet_access_ws__connects(monkeypatch):
    monkeypatch.setattr(
        "apps.access.consumers.ai_engine.recognize_face",
        lambda _img: None,
    )

    communicator = WebsocketCommunicator(application, WS_TABLET_ACCESS)
    connected, _ = await communicator.connect()
    assert connected
    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_tablet_access_ws__unknown_face_denied(monkeypatch):
    monkeypatch.setattr(
        "apps.access.consumers.ai_engine.recognize_face",
        lambda _img: None,
    )

    communicator = WebsocketCommunicator(application, WS_TABLET_ACCESS)
    await communicator.connect()

    await communicator.send_json_to({"type": "FRAME", "image": FAKE_PHOTO_B64})
    response = await communicator.receive_json_from()

    assert response["status"] == "DENIED"
    assert response["variant"] == "denied_unknown"
    log_count = await sync_to_async(AccessLog.objects.count)()
    assert log_count == 0

    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_tablet_access_ws__granted_creates_log_and_opens_turnstile(
    tablet_access_affiliate,
    monkeypatch,
):
    affiliate = tablet_access_affiliate
    turnstile_calls = []

    monkeypatch.setattr(
        "apps.access.consumers.ai_engine.recognize_face",
        lambda _img: affiliate,
    )
    monkeypatch.setattr(
        "apps.access.services.open_turnstile",
        lambda: turnstile_calls.append(True)
        or TurnstilePulseResult(True, "COM_TEST", 1.0),
    )

    communicator = WebsocketCommunicator(application, WS_TABLET_ACCESS)
    await communicator.connect()

    await communicator.send_json_to({"type": "FRAME", "image": FAKE_PHOTO_B64})
    response = await communicator.receive_json_from()

    assert response["status"] == "GRANTED"
    assert response["variant"] == "granted"
    assert response["name"] == affiliate.nombre
    assert turnstile_calls == [True]

    log = await sync_to_async(AccessLog.objects.get)(client=affiliate)
    assert log.resultado is True

    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_tablet_access_ws__expired_membership_denied(
    tablet_access_expired_affiliate,
    monkeypatch,
):
    affiliate = tablet_access_expired_affiliate
    monkeypatch.setattr(
        "apps.access.consumers.ai_engine.recognize_face",
        lambda _img: affiliate,
    )
    monkeypatch.setattr(
        "apps.access.services.open_turnstile",
        lambda: TurnstilePulseResult(True, "COM_TEST", 1.0),
    )

    communicator = WebsocketCommunicator(application, WS_TABLET_ACCESS)
    await communicator.connect()

    await communicator.send_json_to({"type": "FRAME", "image": FAKE_PHOTO_B64})
    response = await communicator.receive_json_from()

    assert response["status"] == "DENIED"
    assert response["variant"] in ("denied_other", "denied_suspended")

    denied_exists = await sync_to_async(
        AccessLog.objects.filter(client=affiliate, resultado=False).exists
    )()
    assert denied_exists

    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_tablet_access_ws__invalid_json_returns_error(monkeypatch):
    monkeypatch.setattr(
        "apps.access.consumers.ai_engine.recognize_face",
        lambda _img: None,
    )

    communicator = WebsocketCommunicator(application, WS_TABLET_ACCESS)
    await communicator.connect()

    await communicator.send_to(text_data="not-json")
    response = await communicator.receive_json_from()

    assert response["status"] == "ERROR"
    assert "json" in response["reason"].lower()

    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_tablet_access_ws__empty_image_returns_error(monkeypatch):
    monkeypatch.setattr(
        "apps.access.consumers.ai_engine.recognize_face",
        lambda _img: None,
    )

    communicator = WebsocketCommunicator(application, WS_TABLET_ACCESS)
    await communicator.connect()

    await communicator.send_json_to({"type": "FRAME", "image": ""})
    response = await communicator.receive_json_from()

    assert response["status"] == "ERROR"
    assert "image" in response["reason"].lower()

    await communicator.disconnect()

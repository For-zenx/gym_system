import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator

from apps.access.ai_engine import OUTCOME_MATCH, OUTCOME_NO_MATCH, FaceMatchResult, TOLERANCE
from apps.access.hardware import TurnstilePulseResult
from apps.access.models import AccessLog
from config.asgi import application

from tests.access.conftest import WS_TABLET_ACCESS
from tests.core.conftest import FAKE_PHOTO_B64


def _match_result(client=None, outcome=OUTCOME_NO_MATCH):
    return FaceMatchResult(
        client=client,
        outcome=outcome if client is None else OUTCOME_MATCH,
        best_distance=0.2 if client is not None else None,
        best_codigo=client.codigo_afiliado if client is not None else None,
        best_nombre=client.nombre if client is not None else None,
        second_distance=None,
        second_codigo=None,
        second_nombre=None,
        margin=None,
        tolerance=TOLERANCE,
        model="large",
    )


def _patch_match_face(monkeypatch, client=None):
    monkeypatch.setattr(
        "apps.access.frame_processing.ai_engine.match_face",
        lambda _img: _match_result(client=client),
    )


def _patch_verify_face(monkeypatch, client=None):
    monkeypatch.setattr(
        "apps.access.frame_processing.ai_engine.verify_face",
        lambda _img, _candidate: _match_result(client=client),
    )


async def _send_two_confirming_frames(communicator):
    await communicator.send_json_to({"type": "FRAME", "image": FAKE_PHOTO_B64})
    first = await communicator.receive_json_from()
    assert first["status"] == "PENDING"
    assert first["variant"] == "confirming"

    await communicator.send_json_to({"type": "FRAME", "image": FAKE_PHOTO_B64})
    return await communicator.receive_json_from()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_tablet_access_ws__connects(monkeypatch):
    _patch_match_face(monkeypatch, client=None)

    communicator = WebsocketCommunicator(application, WS_TABLET_ACCESS)
    connected, _ = await communicator.connect()
    assert connected
    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_tablet_access_ws__unknown_face_denied(monkeypatch):
    _patch_match_face(monkeypatch, client=None)

    communicator = WebsocketCommunicator(application, WS_TABLET_ACCESS)
    await communicator.connect()

    await communicator.send_json_to({"type": "FRAME", "image": FAKE_PHOTO_B64})
    response = await communicator.receive_json_from()

    assert response["status"] == "DENIED"
    assert response["variant"] == "denied_unknown"
    # Unknown faces may create a client-less AccessLog for the feed.
    with_client = await sync_to_async(
        AccessLog.objects.filter(client__isnull=False).count
    )()
    assert with_client == 0

    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_tablet_access_ws__granted_creates_log_and_opens_turnstile(
    tablet_access_affiliate,
    monkeypatch,
):
    affiliate = tablet_access_affiliate
    turnstile_calls = []

    _patch_match_face(monkeypatch, client=affiliate)
    monkeypatch.setattr(
        "apps.access.services.open_turnstile",
        lambda: turnstile_calls.append(True)
        or TurnstilePulseResult(True, "COM_TEST", 1.0),
    )

    communicator = WebsocketCommunicator(application, WS_TABLET_ACCESS)
    await communicator.connect()

    response = await _send_two_confirming_frames(communicator)

    assert response["status"] == "GRANTED"
    assert response["variant"] == "granted"
    assert response["name"] == affiliate.nombre
    assert turnstile_calls == [True]

    log = await sync_to_async(AccessLog.objects.get)(client=affiliate)
    assert log.resultado is True

    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_tablet_access_ws__burst_grants_with_single_final_response(
    tablet_access_affiliate,
    monkeypatch,
):
    affiliate = tablet_access_affiliate
    turnstile_calls = []
    _patch_match_face(monkeypatch, client=affiliate)
    _patch_verify_face(monkeypatch, client=affiliate)
    monkeypatch.setattr(
        "apps.access.services.open_turnstile",
        lambda: turnstile_calls.append(True)
        or TurnstilePulseResult(True, "COM_TEST", 1.0),
    )

    communicator = WebsocketCommunicator(application, WS_TABLET_ACCESS)
    await communicator.connect()
    await communicator.send_json_to(
        {
            "type": "FRAME_BURST",
            "images": [FAKE_PHOTO_B64, FAKE_PHOTO_B64],
        }
    )
    response = await communicator.receive_json_from()

    assert response["status"] == "GRANTED"
    assert response["name"] == affiliate.nombre
    assert turnstile_calls == [True]
    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_tablet_access_ws__burst_rejection_never_exposes_candidate(
    tablet_access_affiliate,
    monkeypatch,
):
    affiliate = tablet_access_affiliate
    _patch_match_face(monkeypatch, client=affiliate)
    _patch_verify_face(monkeypatch, client=None)

    communicator = WebsocketCommunicator(application, WS_TABLET_ACCESS)
    await communicator.connect()
    await communicator.send_json_to(
        {
            "type": "FRAME_BURST",
            "images": [FAKE_PHOTO_B64, FAKE_PHOTO_B64],
        }
    )
    response = await communicator.receive_json_from()

    assert response["status"] == "DENIED"
    assert response["variant"] == "denied_unknown"
    assert response["name"] == ""
    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_tablet_access_ws__expired_membership_denied(
    tablet_access_expired_affiliate,
    monkeypatch,
):
    affiliate = tablet_access_expired_affiliate
    _patch_match_face(monkeypatch, client=affiliate)
    monkeypatch.setattr(
        "apps.access.services.open_turnstile",
        lambda: TurnstilePulseResult(True, "COM_TEST", 1.0),
    )

    communicator = WebsocketCommunicator(application, WS_TABLET_ACCESS)
    await communicator.connect()

    response = await _send_two_confirming_frames(communicator)

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
    _patch_match_face(monkeypatch, client=None)

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
    _patch_match_face(monkeypatch, client=None)

    communicator = WebsocketCommunicator(application, WS_TABLET_ACCESS)
    await communicator.connect()

    await communicator.send_json_to({"type": "FRAME", "image": ""})
    response = await communicator.receive_json_from()

    assert response["status"] == "ERROR"
    assert "image" in response["reason"].lower()

    await communicator.disconnect()

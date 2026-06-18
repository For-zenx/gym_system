import base64
from pathlib import Path

import pytest

ENROLLMENT_FACE_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "enrollment_face.jpeg"

WS_TABLET_ACCESS = "/ws/tablet/acceso/"
WS_TABLET_ENROLLMENT = "/ws/tablet/enrolamiento/"
WS_DASHBOARD = "/ws/dashboard/"


def image_path_to_b64(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return "data:image/jpeg;base64,{}".format(encoded)


@pytest.fixture
def enrollment_face_b64():
    if not ENROLLMENT_FACE_FIXTURE.exists():
        pytest.skip("Missing tests/fixtures/enrollment_face.jpeg")
    return image_path_to_b64(ENROLLMENT_FACE_FIXTURE)


@pytest.fixture
def tablet_access_affiliate(create_client, create_membership):
    affiliate = create_client()
    create_membership(client=affiliate)
    return affiliate


@pytest.fixture
def tablet_access_expired_affiliate(create_client, create_membership):
    from datetime import date, timedelta

    affiliate = create_client()
    create_membership(
        client=affiliate,
        fecha_inicio=date.today() - timedelta(days=60),
        fecha_fin=date.today() - timedelta(days=1),
    )
    return affiliate


async def receive_json_skipping_status(communicator, expected_type, max_messages=6):
    for _ in range(max_messages):
        message = await communicator.receive_json_from()
        if message.get("type") == "tablet_status":
            continue
        assert message.get("type") == expected_type, message
        return message
    pytest.fail("Expected message type {!r} not received".format(expected_type))

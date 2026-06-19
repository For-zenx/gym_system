from datetime import date, timedelta

import pytest

from apps.clients.models import Client
from apps.clients.services import (
    BulkDeleteCountMismatchError,
    bulk_delete_inactive_clients,
    build_inactive_clients_preview,
    get_inactive_clients_queryset,
)
from tests.factories import create_client, create_membership

FIXED_TODAY = date(2026, 6, 19)


def _set_ingreso(client, ingreso_date):
    Client.objects.filter(pk=client.pk).update(fecha_ingreso=ingreso_date)
    client.refresh_from_db()
    return client


@pytest.mark.django_db
def test_get_inactive_clients_queryset__expired_over_one_year_included():
    affiliate = create_client()
    create_membership(
        client=affiliate,
        fecha_inicio=date(2023, 1, 1),
        fecha_fin=date(2024, 1, 1),
    )

    queryset = get_inactive_clients_queryset(1, today=FIXED_TODAY)

    assert list(queryset.values_list("pk", flat=True)) == [affiliate.pk]


@pytest.mark.django_db
def test_get_inactive_clients_queryset__active_membership_excluded():
    affiliate = create_client()
    create_membership(
        client=affiliate,
        fecha_inicio=date(2024, 1, 1),
        fecha_fin=date(2024, 6, 1),
    )
    create_membership(
        client=affiliate,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
    )

    queryset = get_inactive_clients_queryset(1, today=FIXED_TODAY)

    assert not queryset.filter(pk=affiliate.pk).exists()


@pytest.mark.django_db
def test_get_inactive_clients_queryset__queued_membership_excluded():
    affiliate = create_client()
    create_membership(
        client=affiliate,
        fecha_inicio=date(2023, 1, 1),
        fecha_fin=date(2024, 1, 1),
    )
    create_membership(
        client=affiliate,
        fecha_inicio=FIXED_TODAY + timedelta(days=1),
        fecha_fin=FIXED_TODAY + timedelta(days=31),
    )

    queryset = get_inactive_clients_queryset(1, today=FIXED_TODAY)

    assert not queryset.filter(pk=affiliate.pk).exists()


@pytest.mark.django_db
def test_get_inactive_clients_queryset__no_membership_uses_ingreso_date():
    affiliate = _set_ingreso(create_client(), date(2023, 1, 1))

    queryset = get_inactive_clients_queryset(2, today=FIXED_TODAY)

    assert list(queryset.values_list("pk", flat=True)) == [affiliate.pk]


@pytest.mark.django_db
def test_get_inactive_clients_queryset__recent_expiry_excluded():
    affiliate = create_client()
    create_membership(
        client=affiliate,
        fecha_inicio=date(2025, 12, 1),
        fecha_fin=date(2026, 1, 1),
    )

    queryset = get_inactive_clients_queryset(1, today=FIXED_TODAY)

    assert not queryset.filter(pk=affiliate.pk).exists()


@pytest.mark.django_db
def test_build_inactive_clients_preview__returns_count_and_sample():
    affiliate = create_client(nombre="Inactivo Preview")
    create_membership(
        client=affiliate,
        fecha_inicio=date(2023, 1, 1),
        fecha_fin=date(2024, 1, 1),
    )

    preview = build_inactive_clients_preview(1, today=FIXED_TODAY)

    assert preview["count"] == 1
    assert preview["inactivity_years"] == 1
    assert preview["sample_truncated"] is False
    assert preview["sample"][0]["codigo_afiliado"] == affiliate.codigo_afiliado
    assert preview["sample"][0]["inactivity_since"] == "01/01/2024"


@pytest.mark.django_db
def test_bulk_delete_inactive_clients__count_mismatch_raises():
    affiliate = create_client()
    create_membership(
        client=affiliate,
        fecha_inicio=date(2023, 1, 1),
        fecha_fin=date(2024, 1, 1),
    )

    with pytest.raises(BulkDeleteCountMismatchError) as exc_info:
        bulk_delete_inactive_clients(1, expected_count=2, today=FIXED_TODAY)

    assert exc_info.value.actual_count == 1
    assert Client.objects.filter(pk=affiliate.pk).exists()


@pytest.mark.django_db
def test_bulk_delete_inactive_clients__deletes_eligible_only():
    inactive = create_client(codigo_afiliado="M-90001-00")
    create_membership(
        client=inactive,
        fecha_inicio=date(2023, 1, 1),
        fecha_fin=date(2024, 1, 1),
    )
    active = create_client(codigo_afiliado="M-90002-00")
    create_membership(
        client=active,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
    )

    deleted_codes = bulk_delete_inactive_clients(1, expected_count=1, today=FIXED_TODAY)

    assert deleted_codes == [inactive.codigo_afiliado]
    assert not Client.objects.filter(pk=inactive.pk).exists()
    assert Client.objects.filter(pk=active.pk).exists()

import pytest
from django.urls import reverse

from apps.billing.fiscal.hardware import FiscalPrintResult
from tests.helpers import ACCESS_PARAMS, assert_access, login_if_needed


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["reports.view"])],
)
@pytest.mark.django_db
def test_report_view__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    """Legacy ReportView redirects to summary_report when permitted."""
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("billing:report")
    response = client.get(url)
    assert_access(
        response,
        is_logged_in,
        permissions,
        "reports.view",
        url,
        get_login_url,
        success_status=302,
    )
    if is_logged_in and "reports.view" in permissions:
        assert reverse("billing:summary_report") in response.url


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["reports.send"])],
)
@pytest.mark.django_db
def test_report_send__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("billing:report_send")
    response = client.post(url)
    assert_access(
        response,
        is_logged_in,
        permissions,
        "reports.send",
        url,
        get_login_url,
        success_status=302,
    )


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["reports.view"])],
)
@pytest.mark.django_db
def test_fiscal_report__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("billing:fiscal_report")
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, "reports.view", url, get_login_url)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["reports.view"])],
)
@pytest.mark.django_db
def test_summary_report__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("billing:summary_report")
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, "reports.view", url, get_login_url)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["reports.print_x"])],
)
@pytest.mark.django_db
def test_fiscal_report_print__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
    monkeypatch,
):
    monkeypatch.setattr(
        "apps.billing.views.execute_fiscal_report",
        lambda report_type, **kwargs: FiscalPrintResult(success=True, message="OK", simulated=True),
    )
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("billing:fiscal_report_print")
    response = client.post(
        url,
        {"report_type": "X"},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )

    if not is_logged_in:
        assert response.status_code == 302
        assert response.url == get_login_url(url)
    elif "reports.print_x" not in permissions:
        assert response.status_code == 403
    else:
        assert response.status_code == 200
        payload = response.json()
        assert payload.get("success") is True

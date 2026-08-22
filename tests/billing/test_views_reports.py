import pytest
from django.urls import reverse

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

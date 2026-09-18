import pytest
from decimal import Decimal
from django.urls import reverse

from tests.helpers import ACCESS_PARAMS, assert_access, login_if_needed


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["billing.view_invoices"])],
)
@pytest.mark.django_db
def test_invoice_list__access(
    client,
    create_staff_user,
    create_invoice,
    get_login_url,
    is_logged_in,
    permissions,
):
    create_invoice()
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("billing:invoice_list")
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, "billing.view_invoices", url, get_login_url)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["billing.view_invoice_detail"])],
)
@pytest.mark.django_db
def test_invoice_detail__access(
    client,
    create_staff_user,
    create_invoice,
    get_login_url,
    is_logged_in,
    permissions,
):
    invoice = create_invoice()
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("billing:invoice_detail", kwargs={"pk": invoice.pk})
    response = client.get(url)
    assert_access(
        response,
        is_logged_in,
        permissions,
        "billing.view_invoice_detail",
        url,
        get_login_url,
    )


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["billing.view_invoice_detail"])],
)
@pytest.mark.django_db
def test_invoice_ticket_preview__access(
    client,
    create_staff_user,
    create_invoice,
    get_login_url,
    is_logged_in,
    permissions,
):
    invoice = create_invoice(with_line=True)
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("billing:invoice_ticket_preview", kwargs={"pk": invoice.pk})
    response = client.post(url)
    assert_access(
        response,
        is_logged_in,
        permissions,
        "billing.view_invoice_detail",
        url,
        get_login_url,
    )
    if is_logged_in and "billing.view_invoice_detail" in permissions:
        assert response.status_code == 200
        assert "ticket_lines" in response.json()


@pytest.mark.django_db
def test_invoice_ticket_preview__edit_denied_without_permission(
    client,
    create_staff_user,
    create_invoice,
):
    invoice = create_invoice(with_line=True)
    line = invoice.lines.first()
    staff = create_staff_user(permissions=["billing.view_invoice_detail"])
    client.force_login(staff)

    url = reverse("billing:invoice_ticket_preview", kwargs={"pk": invoice.pk})
    altered = (line.amount_ves + Decimal("100.00")).quantize(Decimal("0.01"))
    response = client.post(url, {"line_amount_{}".format(line.pk): str(altered)})

    assert response.status_code == 403
    assert "permiso" in response.json()["error"].lower()


@pytest.mark.django_db
def test_invoice_ticket_preview__edit_allowed_with_permission(
    client,
    create_staff_user,
    create_invoice,
):
    invoice = create_invoice(with_line=True)
    line = invoice.lines.first()
    staff = create_staff_user(
        permissions=["billing.view_invoice_detail", "billing.edit_invoice"]
    )
    client.force_login(staff)

    url = reverse("billing:invoice_ticket_preview", kwargs={"pk": invoice.pk})
    new_amount = (line.amount_ves + Decimal("50.00")).quantize(Decimal("0.01"))
    response = client.post(url, {"line_amount_{}".format(line.pk): str(new_amount)})

    assert response.status_code == 200
    assert response.json()["monto_total"] == str(new_amount)

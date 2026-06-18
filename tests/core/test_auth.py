import pytest
from django.urls import reverse

STAFF_PASSWORD = "testpass123"


@pytest.mark.django_db
def test_login__get_renders_for_anonymous(client):
    response = client.get(reverse("login"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_login__post_valid_credentials_redirects(client, create_staff_user):
    create_staff_user(username="login_test_user", password=STAFF_PASSWORD)

    response = client.post(
        reverse("login"),
        {"username": "login_test_user", "password": STAFF_PASSWORD},
    )

    assert response.status_code == 302
    assert response.url == reverse("dashboard")


@pytest.mark.django_db
def test_login__post_invalid_credentials_stays_on_form(client):
    response = client.post(
        reverse("login"),
        {"username": "nobody", "password": "wrong-password"},
    )

    assert response.status_code == 200


@pytest.mark.django_db
def test_logout__authenticated_redirects_to_login(client, create_staff_user):
    staff = create_staff_user()
    client.force_login(staff)

    response = client.get(reverse("logout"))

    assert response.status_code == 302
    assert response.url == reverse("login")

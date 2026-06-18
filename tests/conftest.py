from urllib.parse import quote

import pytest
from django.urls import reverse

from tests import factories


@pytest.fixture
def get_login_url():
    def _get_login_url(next_url=""):
        return "{}?next={}".format(reverse("login"), quote(next_url))

    return _get_login_url


@pytest.fixture
def create_staff_user(db):
    return factories.create_staff_user


@pytest.fixture
def create_client(db):
    return factories.create_client


@pytest.fixture
def create_plan(db):
    return factories.create_plan


@pytest.fixture
def create_sale_item(db):
    return factories.create_sale_item


@pytest.fixture
def create_staff_role(db):
    return factories.create_staff_role


@pytest.fixture
def create_invoice(db):
    return factories.create_invoice


@pytest.fixture
def create_membership(db):
    return factories.create_membership


@pytest.fixture
def exchange_rate(db):
    return factories.create_exchange_rate()

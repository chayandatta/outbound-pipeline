import pytest
from rest_framework.test import APIClient
from orders.factories import OrderFactory


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def order(db):
    return OrderFactory()

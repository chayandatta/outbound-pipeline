from datetime import timedelta
from unittest.mock import patch
import pytest
from django.utils import timezone
from freezegun import freeze_time
from orders.factories import OrderFactory
from outbound.models import MessageType, OutboundMessageRequest, OutboundStatus


@pytest.mark.django_db
def test_create_new_request(api_client, order):
    url = "/api/outbound/requests/"
    data = {"order_id": order.id, "message_type": MessageType.RESULT}
    response = api_client.post(url, data, format="json")

    assert response.status_code == 201
    assert response.data["status"] == OutboundStatus.RECEIVED
    assert response.data["order"]["id"] == order.id
    assert response.data["order"]["clinic_name"] == order.clinic_name


@pytest.mark.django_db
def test_create_duplicate_request_returns_200(api_client, order):
    existing = OutboundMessageRequest.objects.create(
        order=order,
        message_type=MessageType.RESULT,
        status=OutboundStatus.RECEIVED,
    )
    url = "/api/outbound/requests/"
    data = {"order_id": order.id, "message_type": MessageType.RESULT}
    response = api_client.post(url, data, format="json")

    assert response.status_code == 200
    assert response.data["id"] == existing.id
    assert OutboundMessageRequest.objects.count() == 1


@pytest.mark.django_db
def test_filtering_requests(api_client):
    order1 = OrderFactory(clinic_name="MayoClinic", external_id="EXT-100")
    order2 = OrderFactory(clinic_name="JohnsHopkins", external_id="EXT-200")

    req1 = OutboundMessageRequest.objects.create(
        order=order1, message_type=MessageType.RESULT, status=OutboundStatus.FAILED
    )
    OutboundMessageRequest.objects.create(
        order=order2,
        message_type=MessageType.CANCELLATION,
        status=OutboundStatus.RECEIVED,
    )

    url = (
        "/api/outbound/requests/?"
        "status=FAILED&message_type=RESULT&order__clinic_name=MayoClinic"
    )
    response = api_client.get(url)

    assert response.status_code == 200
    results = response.data["results"] if "results" in response.data else response.data
    assert len(results) == 1
    assert results[0]["id"] == req1.id


@pytest.mark.django_db
def test_retry_action(api_client, order):
    req = OutboundMessageRequest.objects.create(
        order=order,
        message_type=MessageType.RESULT,
        status=OutboundStatus.FAILED,
        retry_count=1,
    )
    url = f"/api/outbound/requests/{req.id}/retry/"

    with patch(
        "outbound.services.deliver_message",
        return_value={"external_id": "EXT-123", "delivered_at": timezone.now()},
    ):
        response = api_client.post(url)

    assert response.status_code == 200
    assert response.data["status"] == OutboundStatus.DELIVERED

    # Retry when retry_count >= 3 is rejected
    req.refresh_from_db()
    req.status = OutboundStatus.FAILED
    req.retry_count = 3
    req.save()

    response2 = api_client.post(url)
    assert response2.status_code == 400
    assert "error" in response2.data


@pytest.mark.django_db
def test_ignore_action(api_client, order):
    req = OutboundMessageRequest.objects.create(
        order=order,
        message_type=MessageType.RESULT,
        status=OutboundStatus.RECEIVED,
    )
    url = f"/api/outbound/requests/{req.id}/ignore/"
    response = api_client.post(url)

    assert response.status_code == 200
    assert response.data["status"] == OutboundStatus.IGNORED

    # DELIVERED request cannot be ignored
    req.status = OutboundStatus.DELIVERED
    req.save()

    response2 = api_client.post(url)
    assert response2.status_code == 400


@pytest.mark.django_db
def test_process_action(api_client, order):
    req = OutboundMessageRequest.objects.create(
        order=order,
        message_type=MessageType.RESULT,
        status=OutboundStatus.RECEIVED,
    )
    url = f"/api/outbound/requests/{req.id}/process/"

    with patch(
        "outbound.services.deliver_message",
        return_value={"external_id": "EXT-999", "delivered_at": timezone.now()},
    ):
        response = api_client.post(url)

    assert response.status_code == 200
    assert response.data["status"] == OutboundStatus.DELIVERED
    assert response.data["external_id"] == "EXT-999"


@pytest.mark.django_db
def test_time_since_update_serializer(api_client, order):
    now = timezone.now()
    with freeze_time(now):
        req = OutboundMessageRequest.objects.create(
            order=order,
            message_type=MessageType.RESULT,
            status=OutboundStatus.RECEIVED,
        )

    # 2 hours later
    with freeze_time(now + timedelta(hours=2)):
        url = f"/api/outbound/requests/{req.id}/"
        response = api_client.get(url)
        assert response.status_code == 200
        assert response.data["time_since_update"] == "2 hours ago"

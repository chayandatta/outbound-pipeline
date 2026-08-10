import threading
import time
from unittest.mock import patch
import pytest
from django.utils import timezone
from orders.factories import OrderFactory
from outbound.exceptions import (
    AlreadyProcessingError,
    PermanentError,
    TransientError,
    TransitionNotAllowed,
)
from outbound.models import MessageType, OutboundMessageRequest, OutboundStatus
from outbound.services import (
    bulk_process_pending,
    deliver_message,
    process_message_request,
)
from support.models import AuditLog


@pytest.mark.django_db
def test_successful_delivery(order):
    req = OutboundMessageRequest.objects.create(
        order=order,
        message_type=MessageType.RESULT,
        status=OutboundStatus.RECEIVED,
    )
    delivered_time = timezone.now()

    with patch(
        "outbound.services.deliver_message",
        return_value={"external_id": "EXT-1001", "delivered_at": delivered_time},
    ):
        result = process_message_request(req.id)

    assert result is True
    req.refresh_from_db()
    assert req.status == OutboundStatus.DELIVERED
    assert req.external_id == "EXT-1001"
    assert req.delivered_at == delivered_time

    # Check AuditLogs: RECEIVED -> PROCESSING, PROCESSING -> DELIVERED
    logs = AuditLog.objects.filter(object_id=req.id)
    actions = [log.action for log in logs]
    assert "RECEIVED -> PROCESSING" in actions
    assert "PROCESSING -> DELIVERED" in actions


@pytest.mark.django_db
def test_transient_error_handling(order):
    req = OutboundMessageRequest.objects.create(
        order=order,
        message_type=MessageType.RESULT,
        status=OutboundStatus.RECEIVED,
        retry_count=0,
    )

    with patch(
        "outbound.services.deliver_message",
        side_effect=TransientError("Network timeout"),
    ):
        result = process_message_request(req.id)

    assert result is False
    req.refresh_from_db()
    assert req.status == OutboundStatus.FAILED
    assert req.retry_count == 1
    assert req.error_message == "Network timeout"


@pytest.mark.django_db
def test_permanent_error_handling(order):
    req = OutboundMessageRequest.objects.create(
        order=order,
        message_type=MessageType.RESULT,
        status=OutboundStatus.RECEIVED,
        retry_count=0,
    )

    with patch(
        "outbound.services.deliver_message",
        side_effect=PermanentError("Invalid destination address"),
    ):
        result = process_message_request(req.id)

    assert result is False
    req.refresh_from_db()
    assert req.status == OutboundStatus.FAILED
    # Permanent errors MUST NOT increment retry_count
    assert req.retry_count == 0
    assert req.error_message == "Invalid destination address"


@pytest.mark.django_db(transaction=True)
def test_concurrency_race_condition():
    order = OrderFactory()
    req = OutboundMessageRequest.objects.create(
        order=order,
        message_type=MessageType.RESULT,
        status=OutboundStatus.RECEIVED,
    )

    results = []
    exceptions = []

    def call_process():
        try:
            res = process_message_request(req.id)
            results.append(res)
        except Exception as e:
            exceptions.append(e)

    with patch(
        "outbound.services.deliver_message",
        return_value={"external_id": "EXT-CONC", "delivered_at": timezone.now()},
    ):
        t1 = threading.Thread(target=call_process)
        t2 = threading.Thread(target=call_process)

        t1.start()
        time.sleep(0.02)
        t2.start()

        t1.join()
        t2.join()

    assert len(results) == 1
    assert results[0] is True
    assert len(exceptions) == 1
    assert isinstance(exceptions[0], (AlreadyProcessingError, TransitionNotAllowed))


@pytest.mark.django_db(transaction=True)
def test_bulk_process_pending_batch_size_and_skip_locked():
    order1 = OrderFactory()
    order2 = OrderFactory()
    order3 = OrderFactory()

    OutboundMessageRequest.objects.create(
        order=order1, message_type=MessageType.RESULT, status=OutboundStatus.RECEIVED
    )
    OutboundMessageRequest.objects.create(
        order=order2, message_type=MessageType.RESULT, status=OutboundStatus.RECEIVED
    )
    OutboundMessageRequest.objects.create(
        order=order3, message_type=MessageType.RESULT, status=OutboundStatus.RECEIVED
    )

    with patch(
        "outbound.services.deliver_message",
        return_value={"external_id": "EXT-BULK", "delivered_at": timezone.now()},
    ):
        # Process with batch_size = 2
        stats = bulk_process_pending(batch_size=2)

    assert stats["processed"] == 2
    assert stats["delivered"] == 2

    # Verify only 2 were processed, 1 remains RECEIVED
    delivered_count = OutboundMessageRequest.objects.filter(
        status=OutboundStatus.DELIVERED
    ).count()
    received_count = OutboundMessageRequest.objects.filter(
        status=OutboundStatus.RECEIVED
    ).count()

    assert delivered_count == 2
    assert received_count == 1


@pytest.mark.django_db
def test_deliver_message_probabilistic():
    order = OrderFactory()
    req = OutboundMessageRequest.objects.create(
        order=order, message_type=MessageType.RESULT
    )
    try:
        res = deliver_message(req)
        assert "external_id" in res
    except (TransientError, PermanentError):
        pass

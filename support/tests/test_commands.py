from io import StringIO
from unittest.mock import patch
import pytest
from django.core.management import call_command
from orders.factories import OrderFactory
from outbound.models import MessageType, OutboundMessageRequest, OutboundStatus


@pytest.mark.django_db
def test_process_pending_dry_run():
    order = OrderFactory()
    OutboundMessageRequest.objects.create(
        order=order, message_type=MessageType.RESULT, status=OutboundStatus.RECEIVED
    )

    out = StringIO()
    call_command("process_pending", "--dry-run", stdout=out)
    output = out.getvalue()

    assert "[DRY RUN]" in output
    assert "Pending records found: 1" in output
    # Count remains RECEIVED
    assert (
        OutboundMessageRequest.objects.filter(status=OutboundStatus.RECEIVED).count()
        == 1
    )


@pytest.mark.django_db
def test_process_pending_execution():
    order = OrderFactory()
    OutboundMessageRequest.objects.create(
        order=order, message_type=MessageType.RESULT, status=OutboundStatus.RECEIVED
    )

    out = StringIO()
    with patch(
        "outbound.services.deliver_message",
        return_value={"external_id": "EXT-CMD", "delivered_at": None},
    ):
        call_command("process_pending", "--batch-size", "10", stdout=out)

    output = out.getvalue()
    assert "Processed: 1 | Delivered: 1 | Failed: 0 | Skipped: 0" in output

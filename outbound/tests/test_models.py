import pytest
from django.db import IntegrityError
from orders.factories import OrderFactory
from outbound.exceptions import TransitionNotAllowed
from outbound.models import (
    MessageType,
    OutboundMessageRequest,
    OutboundStatus,
)
from support.models import AuditLog


@pytest.mark.django_db
def test_valid_state_transitions():
    order = OrderFactory()
    req = OutboundMessageRequest.objects.create(
        order=order,
        message_type=MessageType.RESULT,
        status=OutboundStatus.RECEIVED,
    )
    assert req.status == OutboundStatus.RECEIVED

    # RECEIVED -> PROCESSING
    req.transition_to(OutboundStatus.PROCESSING)
    assert req.status == OutboundStatus.PROCESSING
    assert AuditLog.objects.filter(action="RECEIVED -> PROCESSING").exists()

    # PROCESSING -> DELIVERED
    req.transition_to(OutboundStatus.DELIVERED)
    assert req.status == OutboundStatus.DELIVERED
    assert AuditLog.objects.filter(action="PROCESSING -> DELIVERED").exists()


@pytest.mark.django_db
def test_invalid_state_transitions():
    order = OrderFactory()
    req = OutboundMessageRequest.objects.create(
        order=order,
        message_type=MessageType.RESULT,
        status=OutboundStatus.RECEIVED,
    )

    # Direct RECEIVED -> DELIVERED is invalid
    with pytest.raises(TransitionNotAllowed):
        req.transition_to(OutboundStatus.DELIVERED)

    req.transition_to(OutboundStatus.PROCESSING)
    req.transition_to(OutboundStatus.DELIVERED)

    # DELIVERED -> IGNORED is invalid
    with pytest.raises(TransitionNotAllowed):
        req.transition_to(OutboundStatus.IGNORED)

    # DELIVERED -> PROCESSING is invalid
    with pytest.raises(TransitionNotAllowed):
        req.transition_to(OutboundStatus.PROCESSING)


@pytest.mark.django_db
def test_unique_constraint():
    order = OrderFactory()
    OutboundMessageRequest.objects.create(
        order=order,
        message_type=MessageType.RESULT,
    )

    with pytest.raises(IntegrityError):
        OutboundMessageRequest.objects.create(
            order=order,
            message_type=MessageType.RESULT,
        )


@pytest.mark.django_db
def test_retry_limit_blocks_transition():
    order = OrderFactory()
    req = OutboundMessageRequest.objects.create(
        order=order,
        message_type=MessageType.RESULT,
        status=OutboundStatus.FAILED,
        retry_count=3,
    )

    assert not req.can_transition_to(OutboundStatus.PROCESSING)
    with pytest.raises(TransitionNotAllowed):
        req.transition_to(OutboundStatus.PROCESSING)


@pytest.mark.django_db
def test_ignored_from_valid_states():
    order = OrderFactory()
    # From RECEIVED
    req1 = OutboundMessageRequest.objects.create(
        order=order, message_type=MessageType.RESULT, status=OutboundStatus.RECEIVED
    )
    req1.transition_to(OutboundStatus.IGNORED)
    assert req1.status == OutboundStatus.IGNORED

    # From FAILED
    req2 = OutboundMessageRequest.objects.create(
        order=order, message_type=MessageType.CANCELLATION, status=OutboundStatus.FAILED
    )
    req2.transition_to(OutboundStatus.IGNORED)
    assert req2.status == OutboundStatus.IGNORED

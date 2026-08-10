import random
import uuid
from django.db import DatabaseError, OperationalError, transaction
from django.utils import timezone
from outbound.exceptions import (
    AlreadyProcessingError,
    PermanentError,
    TransientError,
    TransitionNotAllowed,
)
from outbound.models import OutboundMessageRequest, OutboundStatus

try:
    import sqlite3

    SQLITE_ERRORS = (sqlite3.OperationalError, sqlite3.DatabaseError)
except ImportError:
    SQLITE_ERRORS = ()


def deliver_message(request: OutboundMessageRequest) -> dict:
    """Mock external delivery with 70% success, 20% transient, 10% permanent."""
    outcome = random.choices(
        population=["success", "transient", "permanent"],
        weights=[0.7, 0.2, 0.1],
        k=1,
    )[0]

    if outcome == "success":
        return {
            "external_id": f"EXT-{uuid.uuid4()}",
            "delivered_at": timezone.now(),
        }
    elif outcome == "transient":
        raise TransientError("Transient delivery error from mock external service")
    else:
        raise PermanentError("Permanent delivery error from mock external service")


def process_message_request(request_id: int) -> bool:
    """
    RECEIVED -> PROCESSING -> DELIVERED or FAILED.

    Uses select_for_update(nowait=True) inside a transaction.
    Raises AlreadyProcessingError if lock cannot be acquired or if status is PROCESSING.
    Creates AuditLog for every transition.
    """
    with transaction.atomic():
        try:
            req = (
                OutboundMessageRequest.objects.select_for_update(nowait=True)
                .select_related("order")
                .get(id=request_id)
            )
            if req.status == OutboundStatus.PROCESSING:
                raise AlreadyProcessingError(
                    f"Request {request_id} is already in PROCESSING state."
                )

            if not req.can_transition_to(OutboundStatus.PROCESSING):
                msg = (
                    f"Cannot process request {request_id} from state {req.status} "
                    f"with retry_count={req.retry_count}"
                )
                raise TransitionNotAllowed(msg)

            # Transition to PROCESSING (creates AuditLog)
            req.transition_to(OutboundStatus.PROCESSING)
        except (DatabaseError, OperationalError) + SQLITE_ERRORS as err:
            raise AlreadyProcessingError(
                f"Request {request_id} is currently locked by another worker: {err}"
            )
        except OutboundMessageRequest.DoesNotExist:
            raise ValueError(
                f"OutboundMessageRequest with id {request_id} does not exist."
            )

        try:
            result = deliver_message(req)
            req.external_id = result["external_id"]
            req.delivered_at = result["delivered_at"]
            req.transition_to(OutboundStatus.DELIVERED)
            return True
        except TransientError as e:
            req.retry_count += 1
            req.error_message = str(e)
            req.transition_to(OutboundStatus.FAILED)
            return False
        except PermanentError as e:
            # Permanent error: retry_count MUST NOT be incremented
            req.error_message = str(e)
            req.transition_to(OutboundStatus.FAILED)
            return False


def retry_failed_request(request_id: int) -> bool:
    """
    Retry a failed message request.
    Validates retry_count < 3 and status FAILED.
    """
    req = OutboundMessageRequest.objects.get(id=request_id)
    if req.status != OutboundStatus.FAILED:
        raise TransitionNotAllowed(
            f"Cannot retry request in status {req.status}, must be FAILED."
        )
    if req.retry_count >= 3:
        raise TransitionNotAllowed(
            f"Cannot retry request {request_id}: maximum retry limit of 3 reached."
        )

    return process_message_request(request_id)


def bulk_process_pending(batch_size: int = 50) -> dict:
    """
    Process at most batch_size RECEIVED requests using select_for_update(skip_locked=True).
    Returns stats dict: processed, delivered, failed, skipped.
    """
    stats = {
        "processed": 0,
        "delivered": 0,
        "failed": 0,
        "skipped": 0,
    }

    with transaction.atomic():
        # Lock candidate RECEIVED requests, skipping any locked rows
        queryset = list(
            OutboundMessageRequest.objects.filter(
                status=OutboundStatus.RECEIVED
            ).select_for_update(skip_locked=True)[:batch_size]
        )
        request_ids = [r.id for r in queryset]

    # Process each request individually
    for req_id in request_ids:
        try:
            stats["processed"] += 1
            success = process_message_request(req_id)
            if success:
                stats["delivered"] += 1
            else:
                stats["failed"] += 1
        except (AlreadyProcessingError, TransitionNotAllowed):
            stats["skipped"] += 1

    return stats

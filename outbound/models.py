from django.db import models
from orders.models import Order
from outbound.exceptions import TransitionNotAllowed
from support.models import AuditLog


class OutboundStatus(models.TextChoices):
    RECEIVED = "RECEIVED", "Received"
    PROCESSING = "PROCESSING", "Processing"
    DELIVERED = "DELIVERED", "Delivered"
    FAILED = "FAILED", "Failed"
    IGNORED = "IGNORED", "Ignored"


class MessageType(models.TextChoices):
    RESULT = "RESULT", "Result"
    CANCELLATION = "CANCELLATION", "Cancellation"
    AMENDMENT = "AMENDMENT", "Amendment"


class OutboundMessageRequest(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="outbound_requests",
    )
    status = models.CharField(
        max_length=20,
        choices=OutboundStatus.choices,
        default=OutboundStatus.RECEIVED,
    )
    message_type = models.CharField(
        max_length=20,
        choices=MessageType.choices,
    )
    external_id = models.CharField(max_length=255, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    retry_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["order", "message_type"],
                name="unique_order_message_type",
            )
        ]
        ordering = ["-created_at"]

    def can_transition_to(self, target_status: str) -> bool:
        if self.status == target_status:
            return False

        if target_status == OutboundStatus.PROCESSING:
            if self.retry_count >= 3:
                return False
            return self.status in [OutboundStatus.RECEIVED, OutboundStatus.FAILED]

        if target_status == OutboundStatus.DELIVERED:
            return self.status == OutboundStatus.PROCESSING

        if target_status == OutboundStatus.FAILED:
            return self.status == OutboundStatus.PROCESSING

        if target_status == OutboundStatus.IGNORED:
            return self.status != OutboundStatus.DELIVERED

        return False

    def transition_to(self, target_status: str, actor=None, metadata=None) -> None:
        if not self.can_transition_to(target_status):
            msg = (
                f"Cannot transition from {self.status} to {target_status} "
                f"(retry_count={self.retry_count})"
            )
            raise TransitionNotAllowed(msg)

        old_status = self.status
        self.status = target_status
        self.save()

        # Generate AuditLog entry
        log_metadata = {
            "from_status": old_status,
            "to_status": target_status,
            "retry_count": self.retry_count,
        }
        if metadata:
            log_metadata.update(metadata)

        AuditLog.objects.create(
            content_object=self,
            action=f"{old_status} -> {target_status}",
            actor=actor,
            metadata=log_metadata,
        )

    def __str__(self):
        return (
            f"OutboundMessageRequest {self.id} "
            f"({self.order_id} - {self.message_type}: {self.status})"
        )

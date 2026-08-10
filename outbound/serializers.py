from django.utils import timezone
from rest_framework import serializers
from orders.models import Order
from outbound.models import OutboundMessageRequest


def format_time_since(dt, now=None) -> str:
    if not dt:
        return ""
    current_time = now or timezone.now()
    delta = current_time - dt
    total_seconds = max(0, int(delta.total_seconds()))

    if total_seconds < 60:
        return "just now"
    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ["id", "external_id", "patient_name", "clinic_name", "created_at"]


class OutboundMessageRequestSerializer(serializers.ModelSerializer):
    order = OrderSerializer(read_only=True)
    order_id = serializers.PrimaryKeyRelatedField(
        queryset=Order.objects.all(),
        write_only=True,
        source="order",
    )
    time_since_update = serializers.SerializerMethodField()

    class Meta:
        model = OutboundMessageRequest
        fields = [
            "id",
            "order",
            "order_id",
            "status",
            "message_type",
            "external_id",
            "error_message",
            "retry_count",
            "created_at",
            "updated_at",
            "delivered_at",
            "time_since_update",
        ]
        read_only_fields = [
            "id",
            "status",
            "external_id",
            "error_message",
            "retry_count",
            "created_at",
            "updated_at",
            "delivered_at",
        ]
        validators = []

    def get_time_since_update(self, obj) -> str:
        return format_time_since(obj.updated_at)

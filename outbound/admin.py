from django.contrib import admin
from outbound.models import OutboundMessageRequest


@admin.register(OutboundMessageRequest)
class OutboundMessageRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "message_type",
        "status",
        "retry_count",
        "created_at",
    )
    list_filter = ("status", "message_type")
    search_fields = ("order__external_id", "external_id")

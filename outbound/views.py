from django.db import IntegrityError, transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from outbound.exceptions import (
    AlreadyProcessingError,
    TransitionNotAllowed,
)
from outbound.models import OutboundMessageRequest, OutboundStatus
from outbound.serializers import OutboundMessageRequestSerializer
from outbound.services import (
    process_message_request,
    retry_failed_request,
)


class OutboundMessageRequestViewSet(viewsets.ModelViewSet):
    queryset = OutboundMessageRequest.objects.all().select_related("order")
    serializer_class = OutboundMessageRequestSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = {
        "status": ["exact"],
        "message_type": ["exact"],
        "order__external_id": ["exact"],
        "order__clinic_name": ["exact"],
    }

    def create(self, request, *args, **kwargs):
        write_serializer = self.get_serializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)

        order = write_serializer.validated_data["order"]
        message_type = write_serializer.validated_data["message_type"]

        try:
            with transaction.atomic():
                obj, created = OutboundMessageRequest.objects.get_or_create(
                    order=order,
                    message_type=message_type,
                    defaults={"status": OutboundStatus.RECEIVED},
                )
        except IntegrityError:
            # Under concurrent duplicate POSTs, database unique constraint triggers IntegrityError.
            obj = OutboundMessageRequest.objects.get(
                order=order,
                message_type=message_type,
            )
            created = False

        read_serializer = self.get_serializer(obj)
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(read_serializer.data, status=response_status)

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        req = self.get_object()
        try:
            retry_failed_request(req.id)
            req.refresh_from_db()
            return Response(self.get_serializer(req).data, status=status.HTTP_200_OK)
        except (TransitionNotAllowed, ValueError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except AlreadyProcessingError as e:
            return Response({"error": str(e)}, status=status.HTTP_409_CONFLICT)

    @action(detail=True, methods=["post"])
    def ignore(self, request, pk=None):
        req = self.get_object()
        if not req.can_transition_to(OutboundStatus.IGNORED):
            return Response(
                {"error": f"Cannot transition to IGNORED from status {req.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        req.transition_to(OutboundStatus.IGNORED)
        return Response(self.get_serializer(req).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def process(self, request, pk=None):
        req = self.get_object()
        try:
            process_message_request(req.id)
            req.refresh_from_db()
            return Response(self.get_serializer(req).data, status=status.HTTP_200_OK)
        except TransitionNotAllowed as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except AlreadyProcessingError as e:
            return Response({"error": str(e)}, status=status.HTTP_409_CONFLICT)

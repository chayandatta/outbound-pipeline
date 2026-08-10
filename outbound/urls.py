from rest_framework.routers import DefaultRouter
from outbound.views import OutboundMessageRequestViewSet

router = DefaultRouter()
router.register(r"requests", OutboundMessageRequestViewSet, basename="outbound-request")

urlpatterns = router.urls

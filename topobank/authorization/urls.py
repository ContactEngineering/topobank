from django.conf import settings
from rest_framework.routers import DefaultRouter, SimpleRouter

from . import views as v1

app_name = "authorization"

router = DefaultRouter() if settings.DEBUG else SimpleRouter()
router.register(r"v1/permission-set", v1.PermissionSetViewSet, basename="permission-set-v1")

urlpatterns = router.urls

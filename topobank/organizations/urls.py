from django.conf import settings
from rest_framework.routers import DefaultRouter, SimpleRouter

from . import views

app_name = "organizations"

router = DefaultRouter() if settings.DEBUG else SimpleRouter()
router.register(
    r"api/organization", views.OrganizationViewSet, basename="organization-api"
)

urlpatterns = router.urls

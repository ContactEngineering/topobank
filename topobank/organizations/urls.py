from django.conf import settings
from django.urls import path
from rest_framework.routers import DefaultRouter, SimpleRouter

from . import views as v1

app_name = "organizations"

router = DefaultRouter() if settings.DEBUG else SimpleRouter()
router.register(
    r"v1/organization", v1.OrganizationViewSet, basename="organization-v1"
)

urlpatterns = router.urls

urlpatterns += [
    #
    # API routes
    #
    path(
        "v1/add-user/<int:pk>/",
        view=v1.add_user,
        name="add-user-v1",
    ),
    path(
        "v1/remove-user/<int:pk>/",
        view=v1.remove_user,
        name="remove-user-v1",
    ),
]

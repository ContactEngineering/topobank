from django.conf import settings
from django.urls import path
from rest_framework.routers import DefaultRouter, SimpleRouter

from . import views as v1

app_name = "authorization"

router = DefaultRouter() if settings.DEBUG else SimpleRouter()
router.register(
    r"v1/permission-set", v1.PermissionSetViewSet, basename="permission-set-v1"
)

urlpatterns = router.urls

urlpatterns += [
    #
    # API routes
    #
    path(
        "v1/grant-user/<pk>/",
        view=v1.grant_user,
        name="grant-user-v1",
    ),
    path(
        "v1/revoke-user/<pk>/",
        view=v1.revoke_user,
        name="revoke-user-v1",
    ),
    path(
        "v1/grant-organization/<pk>/",
        view=v1.grant_organization,
        name="grant-organization-v1",
    ),
    path(
        "v1/revoke-organization/<pk>/",
        view=v1.revoke_organization,
        name="revoke-organization-v1",
    ),
]

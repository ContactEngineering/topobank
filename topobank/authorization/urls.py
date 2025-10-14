from django.conf import settings
from django.urls import path
from rest_framework.routers import DefaultRouter, SimpleRouter

from . import views as v2

app_name = "authorization"

router = DefaultRouter() if settings.DEBUG else SimpleRouter()
router.register(
    r"v2/permission-set", v2.PermissionSetViewSet, basename="permission-set-v2"
)

urlpatterns = router.urls

urlpatterns += [
    #
    # API routes
    #
    path(
        "v2/grant-user-access/<pk>/",
        view=v2.grant_user,
        name="grant-user-access-v2",
    ),
    path(
        "v2/revoke-user-access/<pk>/",
        view=v2.revoke_user,
        name="revoke-user-access-v2",
    ),
    path(
        "v2/grant-organization-access/<pk>/",
        view=v2.grant_organization,
        name="grant-organization-access-v2",
    ),
    path(
        "v2/revoke-organization-access/<pk>/",
        view=v2.revoke_organization,
        name="revoke-organization-access-v2",
    ),
]

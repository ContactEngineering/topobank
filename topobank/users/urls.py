from django.conf import settings
from django.urls import path
from rest_framework.routers import DefaultRouter, SimpleRouter

from . import views as v1

app_name = "users"

router = DefaultRouter() if settings.DEBUG else SimpleRouter()
router.register(r"v1/user", v1.UserViewSet, basename="user-v1")

urlpatterns = router.urls

urlpatterns += [
    #
    # API routes
    #
    path(
        "v1/add-organization/<int:pk>/",
        view=v1.add_organization,
        name="add-organization-v1",
    ),
    path(
        "v1/remove-organization/<int:pk>/",
        view=v1.remove_organization,
        name="remove-organization-v1",
    ),
]

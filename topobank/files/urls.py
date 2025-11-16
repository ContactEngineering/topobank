from django.conf import settings
from django.urls import path
from rest_framework.routers import DefaultRouter, SimpleRouter

from . import views

app_name = "files"

router = DefaultRouter() if settings.DEBUG else SimpleRouter()
router.register(r"manifest", views.FileManifestViewSet, basename="manifest-api")

urlpatterns = router.urls
urlpatterns += [
    # This route should be renamed, but it is v1. This is a list of manifests in a folder.
    path("folder/<int:pk>/", view=views.list_manifests, name="folder-api-detail")
]

if not settings.USE_S3_STORAGE:
    # If we don't have S3, we need to be able to receive files directly within the
    # files app
    urlpatterns += [
        path(
            "upload/local/<int:manifest_id>/",
            view=views.upload_local,
            name="upload-direct-local",
        )
    ]

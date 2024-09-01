from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "files"

router = DefaultRouter()
router.register(r"manifest", views.FileManifestViewSet, basename="manifest-api")

urlpatterns = router.urls
urlpatterns += [
    path("folder/<int:pk>/", view=views.list_manifests, name="folder-api-detail")
]

if not settings.USE_S3_STORAGE:
    # If we don't have S3, we need to be able to receive files directly within the
    # files app
    urlpatterns += [
        path(
            "upload/local/<int:manifest_id>/",
            view=login_required(views.upload_local),
            name="upload-direct-local",
        )
    ]

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"manifest", views.FileManifestViewSet, basename="manifest-api")

urlpatterns = router.urls

app_name = "files"
urlpatterns += [
    path(
        "upload/finish/<int:manifest_id>/",
        view=login_required(views.upload_finished),
        name="upload-finished",
    ),
]

if not settings.USE_S3_STORAGE:
    urlpatterns += [
        path(
            "upload/local/<int:manifest_id>/",
            view=login_required(views.upload_local),
            name="upload-direct-local",
        )
    ]

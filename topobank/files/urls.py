from django.conf import settings
from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"manifest", views.FileManifestViewSet, basename="manifest-api")

urlpatterns = router.urls

# Note: We only require a login for routes that can change a dataset. We don't
# require a login to see the dataset, because the anonymous user should be
# allowed to see its datasets. (Those are the ones that were published.)

app_name = "files"
urlpatterns += [
    path("upload/start/", view=views.FileDirectUploadStartApi.as_view()),
    path("upload/finish/", view=views.FileDirectUploadFinishApi.as_view()),
]

if not settings.USE_S3_STORAGE:
    urlpatterns += [
        path(
            "upload/local/<str:file_id>/",
            view=views.FileDirectUploadLocalApi.as_view(),
            name="upload-direct-local",
        )
    ]

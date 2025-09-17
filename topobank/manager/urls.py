from django.conf import settings
from django.urls import path, re_path
from rest_framework.routers import DefaultRouter, SimpleRouter

from .v1 import views as v1
from .v2 import views as v2

router = DefaultRouter() if settings.DEBUG else SimpleRouter()
router.register(r"api/tag", v1.TagViewSet, basename="tag-api")
router.register(r"api/topography", v1.TopographyViewSet, basename="topography-api")
router.register(r"api/surface", v1.SurfaceViewSet, basename="surface-api")
router.register(r"v2/topography", v2.TopographyViewSet, basename="topography-v2")
router.register(r"v2/surface", v2.SurfaceViewSet, basename="surface-v2")
router.register(r"v2/zip-container", v2.ZipContainerViewSet, basename="zip-container-v2")

urlpatterns = router.urls

# Note: We only require a login for routes that can change a dataset. We don't
# require a login to see the dataset, because the anonymous user should be
# allowed to see its datasets. (Those are the ones that were published.)

app_name = "manager"
urlpatterns += [
    #
    # Data routes (v1)
    # v1 API creates ZIP container in Django task, which blocks the server
    #
    re_path(
        r"api/surface/(?P<surface_ids>[\d,]+)/download/$",
        view=v1.download_surface,
        name="surface-download",
    ),
    re_path(
        r"api/download-tag/(?P<name>[^.]+)/$",
        view=v1.download_tag,
        name="tag-download",
    ),
    #
    # Data routes (v2)
    # v2 API defers creation of ZIP containers to a Celery task
    #
    # POST
    re_path(
        r"v2/download-surface/(?P<surface_ids>[\d,]+)/$",
        view=v2.download_surface,
        name="surface-download-v2",
    ),
    # POST
    re_path(
        r"v2/download-tag/(?P<name>[^.]+)/$",
        view=v2.download_tag,
        name="tag-download-v2",
    ),
    # POST
    path(
        "v2/upload-zip/start/",
        view=v2.upload_zip_start,
        name="zip-upload-start-v2",
    ),
    # POST
    path(
        "v2/upload-zip/finish/<pk>/",
        view=v2.upload_zip_finish,
        name="zip-upload-finish-v2",
    ),
    #
    # API routes
    #
    path(
        "api/topography/<pk>/force-inspect/",
        view=v1.force_inspect,
        name="force-inspect",
    ),
    path(
        "api/surface/<pk>/set-permissions/",
        view=v1.set_surface_permissions,
        name="set-surface-permissions",
    ),
    re_path(
        r"api/set-tag-permissions/(?P<name>[^.]+)",
        view=v1.set_tag_permissions,
        name="set-tag-permissions",
    ),
    re_path(
        r"api/properties-in-tag/numerical/(?P<name>[^.]+)",
        view=v1.tag_numerical_properties,
        name="numerical-properties",
    ),
    re_path(
        r"api/properties-in-tag/categorical/(?P<name>[^.]+)",
        view=v1.tag_categorical_properties,
        name="categorical-properties",
    ),
    path(
        "api/import-surface/",
        view=v1.import_surface,
        name="import-surface",
    ),
    path("api/versions/", view=v1.versions, name="versions"),
    path("api/statistics/", view=v1.statistics, name="statistics"),
    # GET
    # * Return memory usage of inspection tasks
    path("api/memory-usage/", view=v1.memory_usage, name="memory-usage"),
]

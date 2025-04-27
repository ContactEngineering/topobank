from django.conf import settings
from django.urls import path, re_path
from rest_framework.routers import DefaultRouter, SimpleRouter

from .v1 import views

router = DefaultRouter() if settings.DEBUG else SimpleRouter()
router.register(r"api/tag", views.TagViewSet, basename="tag-api")
router.register(r"api/topography", views.TopographyViewSet, basename="topography-api")
router.register(r"api/surface", views.SurfaceViewSet, basename="surface-api")

urlpatterns = router.urls

# Note: We only require a login for routes that can change a dataset. We don't
# require a login to see the dataset, because the anonymous user should be
# allowed to see its datasets. (Those are the ones that were published.)

app_name = "manager"
urlpatterns += [
    #
    # Data routes (v1)
    #
    re_path(
        r"api/surface/(?P<surface_ids>[\d,]+)/download/$",
        view=views.download_surface,
        name="surface-download",
    ),
    re_path(
        r"api/download-tag/(?P<name>[^.]+)/$",
        view=views.download_tag,
        name="tag-download",
    ),
    #
    # Data routes (v2)
    #
    re_path(
        r"api/download-surface/(?P<surface_ids>[\d,]+)$",
        view=views.download_surface,
        name="surface-download",
    ),
    re_path(
        r"api/download-tag/(?P<name>[^.]+)/$",
        view=views.download_tag,
        name="tag-download",
    ),
    #
    # API routes
    #
    path(
        "api/topography/<pk>/force-inspect/",
        view=views.force_inspect,
        name="force-inspect",
    ),
    path(
        "api/surface/<pk>/set-permissions/",
        view=views.set_surface_permissions,
        name="set-surface-permissions",
    ),
    re_path(
        r"api/set-tag-permissions/(?P<name>[^.]+)",
        view=views.set_tag_permissions,
        name="set-tag-permissions",
    ),
    re_path(
        r"api/properties-in-tag/numerical/(?P<name>[^.]+)",
        view=views.tag_numerical_properties,
        name="numerical-properties",
    ),
    re_path(
        r"api/properties-in-tag/categorical/(?P<name>[^.]+)",
        view=views.tag_categorical_properties,
        name="categorical-properties",
    ),
    path(
        "api/import-surface/",
        view=views.import_surface,
        name="import-surface",
    ),
    path("api/versions/", view=views.versions, name="versions"),
    path("api/statistics/", view=views.statistics, name="statistics"),
    # GET
    # * Return memory usage of inspection tasks
    path("api/memory-usage/", view=views.memory_usage, name="memory-usage"),
]

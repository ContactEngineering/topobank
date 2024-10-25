from django.contrib.auth.decorators import login_required
from django.urls import path, re_path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"api/tag", views.TagViewSet, basename="tag-api")
router.register(r"api/topography", views.TopographyViewSet, basename="topography-api")
router.register(r"api/surface", views.SurfaceViewSet, basename="surface-api")
router.register(r"api/property", views.PropertyViewSet, basename="property-api")

urlpatterns = router.urls

# Note: We only require a login for routes that can change a dataset. We don't
# require a login to see the dataset, because the anonymous user should be
# allowed to see its datasets. (Those are the ones that were published.)

app_name = "manager"
urlpatterns += [
    #
    # Data routes
    #
    re_path(
        r"api/surface/(?P<surface_id>\d+)/download/$",
        view=views.download_surface,
        name="surface-download",
    ),
    #
    # API routes
    #
    path(
        "api/topography/<pk>/force-inspect/",
        view=login_required(views.force_inspect),
        name="force-inspect",
    ),
    path(
        "api/set-surface-permissions/<pk>",
        view=login_required(views.set_surface_permissions),
        name="set-surface-permissions",
    ),
    re_path(
        r"api/set-tag-permissions/<(?P<name>[^.]+)>",
        view=login_required(views.set_tag_permissions),
        name="set-tag-permissions",
    ),
    path(
        "api/tag-numerical-properties/<pk>/",
        view=login_required(views.tag_numerical_properties),
        name="numerical-properties",
    ),
    path(
        "api/tag-categorical-properties/<pk>/",
        view=login_required(views.tag_categorical_properties),
        name="categorical-properties",
    ),
    path(
        "api/import-surface/",
        view=login_required(views.import_surface),
        name="import-surface",
    ),
    path("api/versions/", view=views.versions, name="versions"),
    path("api/statistics/", view=views.statistics, name="statistics"),
    # GET
    # * Return memory usage of inspection tasks
    path("api/memory-usage/", view=views.memory_usage, name="memory-usage"),
]

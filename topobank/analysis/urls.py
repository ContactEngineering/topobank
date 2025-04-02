from django.conf import settings
from django.urls import path, re_path
from rest_framework.routers import DefaultRouter, SimpleRouter

import topobank.analysis.v1.views as v1

from . import downloads, workflows

router = DefaultRouter() if settings.DEBUG else SimpleRouter()
router.register(r"api/configuration", v1.ConfigurationView, basename="configuration")
router.register(r"api/workflow", v1.WorkflowView, basename="workflow")
router.register(r"api/result", v1.ResultView, basename="result")

urlpatterns = router.urls

app_name = workflows.APP_NAME
urlpatterns += [
    #
    # v1 API routes
    #
    # GET
    # * Get pending or running analyses
    path("api/pending", view=v1.pending, name="pending"),
    # GET
    # * Get dependent analyses
    path(
        "api/result/<int:workflow_id>/dependencies",
        view=v1.dependencies,
        name="dependencies",
    ),
    # POST
    # * Set a name, protecting analysis from deletion
    path("api/result/<int:workflow_id>/set-name", view=v1.set_name, name="set-name"),
    # GET
    # * Return named/save results
    path(
        "api/named-result",
        view=v1.named_result,
        name="named-result-list",
    ),
    # GET
    # * Triggers analyses if not yet running
    # * Return state of analyses
    # * Return plot configuration for finished analyses
    # This is a post request because the request parameters are complex.
    path(
        f"api/card/{workflows.VIZ_SERIES}/<str:workflow>",
        view=v1.series_card_view,
        name=f"card-{workflows.VIZ_SERIES}",
    ),
    # GET
    # * Return total number of analyses
    path("api/statistics/", view=v1.statistics, name="statistics"),
    # GET
    # * Return memory usage of individual analyses
    path("api/memory-usage/", view=v1.memory_usage, name="memory-usage"),
    #
    # Data routes (returned data type is unspecified)
    #
    # GET
    # * Returns a redirect to the actual data file in the storage (S3) system
    # The files that can be returned depend on the analysis. This route simply
    # redirects to the storage. It is up to the visualization application to
    # request the correct files.
    re_path(
        r"download/(?P<ids>[\d,]+)/(?P<file_format>\w+)$",
        view=downloads.download_analyses,
        name="download",
    ),

    #
    # v2 API routes
    #
]

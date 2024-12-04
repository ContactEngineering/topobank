from django.urls import path, re_path
from rest_framework.routers import DefaultRouter

from . import downloads, functions, views

router = DefaultRouter()
router.register(r"api/configuration", views.ConfigurationView, basename="configuration")
router.register(r"api/function", views.AnalysisFunctionView, basename="function")
router.register(r"api/result", views.AnalysisResultView, basename="result")

urlpatterns = router.urls

app_name = functions.APP_NAME
urlpatterns += [
    #
    # API routes
    #
    # GET
    # * Get dependent analyses
    path(
        "api/dependencies/<int:analysis_id>",
        view=views.dependencies,
        name="dependencies",
    ),
    # * Return named/save results
    path(
        "api/named-result",
        view=views.named_result,
        name="named-result-list",
    ),
    # GET
    # * Triggers analyses if not yet running
    # * Return state of analyses
    # * Return plot configuration for finished analyses
    # This is a post request because the request parameters are complex.
    path(
        f"api/card/{functions.VIZ_SERIES}/<int:function_id>",
        view=views.series_card_view,
        name=f"card-{functions.VIZ_SERIES}",
    ),
    # GET
    # * Return total number of analyses
    path("api/statistics/", view=views.statistics, name="statistics"),
    # GET
    # * Return memory usage of individual analyses
    path("api/memory-usage/", view=views.memory_usage, name="memory-usage"),
    # POST
    # * Set a name, protecting analysis from deletion
    path("api/set-name/<int:analysis_id>", view=views.set_name, name="set-name"),
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
]

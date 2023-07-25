from django.urls import path, re_path

from rest_framework.routers import DefaultRouter

from . import downloads
from . import functions
from . import views

router = DefaultRouter()
router.register(r'status', views.AnalysisResultView, basename='status')

urlpatterns = router.urls

app_name = functions.APP_NAME
urlpatterns += [
    #
    # HTML routes
    #
    path(
        'html/list/',  # TODO change to 'function', also rename name
        view=views.AnalysesResultListView.as_view(),
        name='results-list'
    ),
    path(
        r'html/detail/<int:pk>/',
        view=views.AnalysisResultDetailView.as_view(),
        name='results-detail'
    ),
    #
    # API routes
    #
    # GET
    # Return function implementations
    path(
        'api/registry/',
        view=views.registry_view,
        name='registry'
    ),
    # GET
    # * Triggers analyses if not yet running
    # * Return state of analyses
    # * Return plot configuration for finished analyses
    # This is a post request because the request parameters are complex.
    path(
        f'api/card/{functions.VIZ_SERIES}/<int:function_id>',
        view=views.series_card_view,
        name=f'card-{functions.VIZ_SERIES}'
    ),
    #
    # Data routes (returned data type is unspecified)
    #
    # GET
    # * Returns a redirect to the actualy data file in the storage (S3) system
    # The files that can be returned depend on the analysis. This route simply
    # redirects to the storage. It is up to the visualization application to
    # request the correct files.
    re_path(
        r'data/(?P<pk>\d+)/(?P<location>.*)$',
        view=views.data,
        name='data'
    ),
    re_path(
        r'download/(?P<ids>[\d,]+)/(?P<file_format>\w+)$',
        view=downloads.download_analyses,
        name='download'
    )
]

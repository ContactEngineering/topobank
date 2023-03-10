from django.urls import path, re_path
from django.contrib.auth.decorators import login_required

from rest_framework.routers import DefaultRouter

from . import downloads
from . import functions
from . import views

router = DefaultRouter()
router.register(r'status', views.AnalysisView, basename='status')

print(router.urls)

urlpatterns = router.urls

app_name = "analysis"
urlpatterns += [
    #
    # HTML routes
    #
    path(
        'list/',  # TODO change to 'function', also rename name
        view=login_required(views.AnalysesListView.as_view()),
        name='list'
    ),
    path(
        'collection/<int:collection_id>/',
        view=login_required(views.AnalysesListView.as_view()),
        name='collection'
    ),
    path(
        'surface/<int:surface_id>/',
        view=login_required(views.AnalysesListView.as_view()),
        name='surface'
    ),
    path(
        'topography/<int:topography_id>/',
        view=login_required(views.AnalysesListView.as_view()),
        name='topography'
    ),
    re_path(
        r'download/(?P<ids>[\d,]+)/(?P<art>[\w\s]+)/(?P<file_format>\w+)$',
        view=login_required(downloads.download_analyses),
        name='download'
    ),
    re_path(
        r'function/(?P<pk>[\d,]+)/$',
        view=login_required(views.AnalysisFunctionDetailView.as_view()),
        name='function-detail'
    ),
    #
    # API routes that return empty JSON
    #
    path(
        'card/submit/',
        view=login_required(views.submit_analyses_view),
        name='card-submit'
    ),
    # POST
    # * Triggers analyses if not yet running
    # * Return state of analyses
    # * Return plot configuration for finished analyses
    # This is a post request because the request parameters are complex.
    path(
        f'card/{functions.VIZ_SERIES}',
        view=login_required(views.series_card_view),
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
        view=login_required(views.data),
        name='data'
    )
]

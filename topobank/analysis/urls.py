from django.urls import path, re_path
from django.contrib.auth.decorators import login_required

from . import views
from . import downloads

app_name = "analysis"
urlpatterns = [
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
    path(
        'card/submit/',
        view=login_required(views.submit_analyses_view),
        name='card-submit'
    ),
    re_path(
        r'data/(?P<pk>\d+)/(?P<location>.*)$',
        view=login_required(views.data),
        name='data'
    ),
    path(
        'card/',
        view=login_required(views.switch_card_view),
        name='card'
    ),
]

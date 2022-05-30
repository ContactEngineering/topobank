from django.conf.urls import url
from django.urls import path
from django.contrib.auth.decorators import login_required

from . import views
from . import downloads

app_name = "analysis"
urlpatterns = [
    url(
        regex=r'list/$',  # TODO change to 'function', also rename name
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
    url(
        regex=r'download/(?P<ids>[\d,]+)/(?P<card_view_flavor>[\w\s]+)/(?P<file_format>\w+)$',
        view=login_required(downloads.download_analyses),
        name='download'
    ),
    url(
        regex=r'function/(?P<pk>[\d,]+)/$',
        view=login_required(views.AnalysisFunctionDetailView.as_view()),
        name='function-detail'
    ),
    url(
        regex=r'card/submit$',
        view=login_required(views.submit_analyses_view),
        name='card-submit'
    ),
    url(
        regex=r'data/(?P<pk>\d+)/(?P<location>.*)$',
        view=login_required(views.data),
        name='data'
    ),
    url(
        regex=r'card/$',
        view=login_required(views.switch_card_view),
        name='card'
    ),
]

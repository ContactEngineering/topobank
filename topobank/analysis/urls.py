from django.conf.urls import url
from django.contrib.auth.decorators import login_required

from . import views

app_name = "analysis"
urlpatterns = [
    url(
        regex=r'list/$',
        view=login_required(views.AnalysisListView.as_view()),
        name='list'
    ),
    url(
        regex=r'(?P<pk>\d+)/retrieve/$',
        view=login_required(views.AnalysisRetrieveView.as_view()),
        name='retrieve'
    ),
    url(
        regex=r'(?P<ids>[\d,]+)/download/txt$',
        view=login_required(views.download_analysis_to_txt),
        name='download-txt'
    ),
    url(
        regex=r'(?P<ids>[\d,]+)/download/xlsx$',
        view=login_required(views.download_analysis_to_xlsx),
        name='download-xlsx'
    ),
]

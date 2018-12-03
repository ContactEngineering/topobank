from django.conf.urls import url
from django.contrib.auth.decorators import login_required

from . import views

app_name = "analysis"
urlpatterns = [
    url(
        regex=r'list/$',
        view=login_required(views.AnalysesView.as_view()),
        name='list'
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
    url(
        regex=r'card/$',
        view=login_required(views.function_result_card),
        name='card'
    ),
]

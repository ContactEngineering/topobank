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
        view=login_required(views.AnalysisDetailView.as_view()),
        name='retrieve'
    ),

]

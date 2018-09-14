from django.conf.urls import url
from django.contrib.auth.decorators import login_required

from . import views

app_name = "analysis"
urlpatterns = [
    url(
        regex=r'$',
        view=login_required(views.AnalysisListView.as_view()),
        name='list'
    ),
]

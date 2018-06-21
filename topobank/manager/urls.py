from django.conf.urls import url
from django.contrib.auth.decorators import login_required
from django.conf import settings

from . import views

app_name = "manager"
urlpatterns = [
    url(
        regex=r'',
        view=login_required(views.TopographyListView.as_view()),
        name='list'
    ),
    url(
        regex=r'~(?P<pk>\d+)/',
        view=login_required(views.TopographyDetailView.as_view()),
        name='detail'
    ),
    url(
        regex=r'~new/',
        view=login_required(views.TopographyCreateView.as_view()),
        name='create'
    ),

]

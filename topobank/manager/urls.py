from django.conf.urls import url
from django.contrib.auth.decorators import login_required

from . import views

app_name = "manager"
urlpatterns = [
    url(
        regex='(?P<pk>\d+)/$',
        view=login_required(views.TopographyDetailView.as_view()),
        name='detail'
    ),
    url(
        regex='(?P<pk>\d+)/update/$',
        view=login_required(views.TopographyUpdateView.as_view()),
        name='update'
    ),
    url(
        regex='(?P<pk>\d+)/delete/$',
        view=login_required(views.TopographyDeleteView.as_view()),
        name='delete'
    ),
    url(
        regex=r'create/$',
        view=login_required(views.TopographyCreateView.as_view()),
        name='create'
    ),
    url(
        regex=r'$',
        view=login_required(views.TopographyListView.as_view()),
        name='list'
    ),

]

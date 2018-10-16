from django.conf.urls import url
from django.contrib.auth.decorators import login_required

from . import views

app_name = "manager"
urlpatterns = [
    url(
        regex=r'topography/(?P<pk>\d+)/$',
        view=login_required(views.TopographyDetailView.as_view()),
        name='topography-detail'
    ),
    url(
        regex=r'topography/(?P<pk>\d+)/update/$',
        view=login_required(views.TopographyUpdateView.as_view()),
        name='topography-update'
    ),
    url(
        regex=r'topography/(?P<pk>\d+)/delete/$',
        view=login_required(views.TopographyDeleteView.as_view()),
        name='topography-delete'
    ),
    # url( # TODO needed?
    #     regex=r'topography/(?P<pk>\d+)/toggle-select/$',
    #     view=login_required(views.toggle_topography_selection),
    #     name='topography-toggle-select'
    # ),
    # url( # TODO needed?
    #     regex=r'topography/(?P<pk>\d+)/is-selected/$',
    #     view=login_required(views.is_topography_selected),
    #     name='topography-is-selected'
    # ),
    # url( # TODO needed?
    #     regex=r'topography/$',
    #     view=login_required(views.SelectedTopographyView.as_view()),
    #     name='topography-list'
    # ),
    url(
        regex=r'surface/(?P<surface_id>\d+)/new-topography/$',
        # view=login_required(views.TopographyCreateView.as_view()),
        view=login_required(views.TopographyCreateWizard.as_view()),
        name='topography-create'
    ),
    url(
        regex=r'surface/(?P<pk>\d+)/$',
        view=login_required(views.SurfaceDetailView.as_view()),
        name='surface-detail'
    ),
    url(
        regex=r'surface/(?P<pk>\d+)/update/$',
        view=login_required(views.SurfaceUpdateView.as_view()),
        name='surface-update'
    ),
    url(
       regex=r'surface/(?P<pk>\d+)/delete/$',
       view=login_required(views.SurfaceDeleteView.as_view()),
       name='surface-delete'
    ),
    url(
        regex=r'surface/new/$',
        view=login_required(views.SurfaceCreateView.as_view()),
        name='surface-create'
    ),
    url(
        regex=r'surface/$',
        view=login_required(views.SurfaceListView.as_view()),
        name='surface-list'
    ),
]

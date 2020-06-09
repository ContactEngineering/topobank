from django.conf.urls import url
from django.contrib.auth.decorators import login_required
from django.views.generic import TemplateView

from . import views
from . import forms


WIZARD_FORMS = [
    ('upload', forms.TopographyFileUploadForm),
    ('metadata', forms.TopographyMetaDataForm),
    ('units', forms.TopographyWizardUnitsForm),
]

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
    url(
        regex=r'topography/(?P<pk>\d+)/select/$',
        view=login_required(views.select_topography),
        name='topography-select'
    ),
    url(
        regex=r'topography/(?P<pk>\d+)/unselect/$',
        view=login_required(views.unselect_topography),
        name='topography-unselect'
    ),
    url(
        regex=r'surface/(?P<surface_id>\d+)/new-topography/$',
        view=login_required(views.TopographyCreateWizard.as_view(WIZARD_FORMS)),
        name='topography-create'
    ),
    url(
        regex=r'surface/(?P<surface_id>\d+)/new-topography/corrupted$',
        view=login_required(views.CorruptedTopographyView.as_view()),
        name='topography-corrupted'
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
       regex=r'surface/(?P<pk>\d+)/share/$',
       view=login_required(views.SurfaceShareView.as_view()),
       name='surface-share'
    ),
    url(
       regex=r'surface/(?P<pk>\d+)/select/$',
       view=login_required(views.select_surface),
       name='surface-select'
    ),
    url(
       regex=r'surface/(?P<pk>\d+)/unselect/$',
       view=login_required(views.unselect_surface),
       name='surface-unselect'
    ),
    url(
        regex=r'surface/(?P<surface_id>\d+)/download/$',
        view=login_required(views.download_surface),
        name='surface-download'
    ),
    url(
        regex=r'surface/new/$',
        view=login_required(views.SurfaceCreateView.as_view()),
        name='surface-create'
    ),
    url(
        regex=r'tag/tree/$',
        view=login_required(views.TagTreeView.as_view()),
        name='tag-list'  # TODO rename
    ),
    url(
       regex=r'tag/(?P<pk>\d+)/select/$',
       view=login_required(views.select_tag),
       name='tag-select'
    ),
    url(
       regex=r'tag/(?P<pk>\d+)/unselect/$',
       view=login_required(views.unselect_tag),
       name='tag-unselect'
    ),
    url(
        regex=r'select/$',
        view=login_required(views.SelectView.as_view()),
        name='select'
    ),
    url(
       regex=r'unselect/$',
       view=login_required(views.unselect_all),
       name='unselect-all'
    ),
    url(
        regex=r'surface/search/$',  # TODO check URL, rename?
        view=login_required(views.SurfaceListView.as_view()),  # TODO Check view name, rename?
        name='search'  # TODO rename?
    ),
    url(
        regex=r'access-denied/$',
        view=TemplateView.as_view(template_name="403.html"),
        name='access-denied'
    ),
    url(
        regex=r'sharing/$',
        view=login_required(views.sharing_info),
        name='sharing-info'
    ),
]

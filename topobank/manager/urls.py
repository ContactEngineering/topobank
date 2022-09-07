from django.conf.urls import re_path
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
    re_path(
        regex=r'topography/(?P<pk>\d+)/$',
        view=login_required(views.TopographyDetailView.as_view()),
        name='topography-detail'
    ),
    re_path(
        regex=r'topography/(?P<pk>\d+)/update/$',
        view=login_required(views.TopographyUpdateView.as_view()),
        name='topography-update'
    ),
    re_path(
        regex=r'topography/(?P<pk>\d+)/delete/$',
        view=login_required(views.TopographyDeleteView.as_view()),
        name='topography-delete'
    ),
    re_path(
        regex=r'topography/(?P<pk>\d+)/select/$',
        view=login_required(views.select_topography),
        name='topography-select'
    ),
    re_path(
        regex=r'topography/(?P<pk>\d+)/unselect/$',
        view=login_required(views.unselect_topography),
        name='topography-unselect'
    ),
    re_path(
        regex=r'topography/(?P<pk>\d+)/thumbnail/$',
        view=login_required(views.thumbnail),
        name='topography-thumbnail'
    ),
    re_path(
        regex=r'topography/(?P<pk>\d+)/dzi/(?P<dzi_filename>.*)$',
        view=login_required(views.dzi),
        name='topography-dzi'
    ),
    re_path(
        regex=r'topography/(?P<pk>\d+)/plot/$',
        view=login_required(views.topography_plot),
        name='topography-plot'
    ),
    re_path(
        regex=r'surface/(?P<surface_id>\d+)/new-topography/$',
        view=login_required(views.TopographyCreateWizard.as_view(WIZARD_FORMS)),
        name='topography-create'
    ),
    re_path(
        regex=r'surface/(?P<surface_id>\d+)/new-topography/corrupted$',
        view=login_required(views.CorruptedTopographyView.as_view()),
        name='topography-corrupted'
    ),
    re_path(
        regex=r'surface/(?P<pk>\d+)/$',
        view=login_required(views.SurfaceDetailView.as_view()),
        name='surface-detail'
    ),
    re_path(
        regex=r'surface/(?P<pk>\d+)/update/$',
        view=login_required(views.SurfaceUpdateView.as_view()),
        name='surface-update'
    ),
    re_path(
       regex=r'surface/(?P<pk>\d+)/delete/$',
       view=login_required(views.SurfaceDeleteView.as_view()),
       name='surface-delete'
    ),
    re_path(
       regex=r'surface/(?P<pk>\d+)/share/$',
       view=login_required(views.SurfaceShareView.as_view()),
       name='surface-share'
    ),
    re_path(
       regex=r'surface/(?P<pk>\d+)/publish/$',
       view=login_required(views.SurfacePublishView.as_view()),
       name='surface-publish'
    ),
    re_path(
        regex=r'surface/(?P<pk>\d+)/publication-rate-too-high/$',
        view=login_required(views.PublicationRateTooHighView.as_view()),
        name='surface-publication-rate-too-high'
    ),
    re_path(
        regex=r'surface/(?P<pk>\d+)/publication-error/$',
        view=login_required(views.PublicationErrorView.as_view()),
        name='surface-publication-error'
    ),
    re_path(
       regex=r'surface/(?P<pk>\d+)/select/$',
       view=login_required(views.select_surface),
       name='surface-select'
    ),
    re_path(
       regex=r'surface/(?P<pk>\d+)/unselect/$',
       view=login_required(views.unselect_surface),
       name='surface-unselect'
    ),
    re_path(
        regex=r'surface/(?P<surface_id>\d+)/download/$',
        view=login_required(views.download_surface),
        name='surface-download'
    ),
    re_path(
        regex=r'surface/new/$',
        view=login_required(views.SurfaceCreateView.as_view()),
        name='surface-create'
    ),
    re_path(
        regex=r'tag/tree/$',
        view=login_required(views.TagTreeView.as_view()),
        name='tag-list'  # TODO rename
    ),
    re_path(
       regex=r'tag/(?P<pk>\d+)/select/$',
       view=login_required(views.select_tag),
       name='tag-select'
    ),
    re_path(
       regex=r'tag/(?P<pk>\d+)/unselect/$',
       view=login_required(views.unselect_tag),
       name='tag-unselect'
    ),
    re_path(
        regex=r'select/$',
        view=login_required(views.SelectView.as_view()),
        name='select'
    ),
    re_path(
        regex=r'select/download$',
        view=login_required(views.download_selection_as_surfaces),
        name='download-selection'
    ),
    re_path(
       regex=r'unselect-all/$',
       view=login_required(views.unselect_all),
       name='unselect-all'
    ),
    re_path(
        regex=r'surface/search/$',  # TODO check URL, rename?
        view=login_required(views.SurfaceListView.as_view()),  # TODO Check view name, rename?
        name='search'  # TODO rename?
    ),
    re_path(
        regex=r'access-denied/$',
        view=TemplateView.as_view(template_name="403.html"),
        name='access-denied'
    ),
    re_path(
        regex=r'sharing/$',
        view=login_required(views.sharing_info),
        name='sharing-info'
    ),
    re_path(
        regex=r'publications/$',
        view=login_required(views.PublicationListView.as_view()),
        name='publications'
    ),
]

from django.conf.urls import url
from django.contrib.auth.decorators import login_required
from django.views.generic import TemplateView

from . import views
from .utils import get_topography_file
from . import forms

def creating_2D_topography(wizard):

    step0_data = wizard.get_cleaned_data_for_step('upload')
    if step0_data is None:
        return False

    datafile = step0_data['datafile']
    step1_data = wizard.get_cleaned_data_for_step('metadata')

    if step1_data is None:
        return False

    topofile = get_topography_file(datafile.file.name)
    topo = topofile.topography(int(step1_data['data_source']))

    return topo.dim == 2

WIZARD_FORMS = [
    ('upload', forms.TopographyFileUploadForm),
    ('metadata', forms.TopographyMetaDataForm),
    ('units1D', forms.Topography1DUnitsForm),
    ('units2D', forms.Topography2DUnitsForm),
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
        regex=r'surface/(?P<surface_id>\d+)/new-topography/$',
        view=login_required(views.TopographyCreateWizard.as_view(
            WIZARD_FORMS,
            condition_dict={
                'units2D': creating_2D_topography,
                'units1D': lambda w: not creating_2D_topography(w),
            }
        )),
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
       regex=r'surface/(?P<pk>\d+)/share/$',
       view=login_required(views.SurfaceShareView.as_view()),
       name='surface-share'
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

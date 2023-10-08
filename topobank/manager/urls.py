from django.urls import re_path, path
from django.contrib.auth.decorators import login_required
from django.views.generic import TemplateView

from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'api/surface', views.SurfaceViewSet, basename='surface-api')
router.register(r'api/topography', views.TopographyViewSet, basename='topography-api')

urlpatterns = router.urls

# Note: We only require a login for routes that can change a dataset. We don't
# require a login to see the dataset, because the anonymous user should be
# allowed to see its datasets. (Those are the ones that were published.)

app_name = "manager"
urlpatterns += [
    #
    # HTML routes
    #
    path(
        r'html/topography/',
        view=views.TopographyDetailView.as_view(),
        name='topography-detail'
    ),
    path(
        r'html/surface/',
        view=views.SurfaceDetailView.as_view(),
        name='surface-detail'
    ),
    re_path(
        r'html/surface/(?P<pk>\d+)/publish/$',
        view=login_required(views.SurfacePublishView.as_view()),
        name='surface-publish'
    ),
    re_path(
        r'html/surface/(?P<pk>\d+)/publication-rate-too-high/$',
        view=login_required(views.PublicationRateTooHighView.as_view()),
        name='surface-publication-rate-too-high'
    ),
    re_path(
        r'html/surface/(?P<pk>\d+)/publication-error/$',
        view=login_required(views.PublicationErrorView.as_view()),
        name='surface-publication-error'
    ),
    path(
        'html/select/',
        view=views.SelectView.as_view(),
        name='select'
    ),
    path(
        'html/access-denied/',
        view=TemplateView.as_view(template_name="403.html"),
        name='access-denied'
    ),
    #
    # Data routes
    #
    re_path(
        r'api/topography/(?P<pk>\d+)/dzi/(?P<dzi_filename>.*)$',
        view=views.dzi,
        name='topography-dzi'
    ),
    path(
        'select/download/',
        view=views.download_selection_as_surfaces,
        name='download-selection'
    ),
    re_path(
        r'api/surface/(?P<surface_id>\d+)/download/$',
        view=views.download_surface,
        name='surface-download'
    ),
    #
    # API routes
    #
    path(
        'api/search/',  # TODO check URL, rename?
        view=views.SurfaceListView.as_view(),  # TODO Check view name, rename?
        name='search'  # TODO rename?
    ),
    path(
        'api/tag-tree/',
        view=views.TagTreeView.as_view(),
        name='tag-list'  # TODO rename
    ),
    path(
        'api/surface/<pk>/set-permissions/',
        view=login_required(views.set_permissions),
        name='set-permissions'
    ),
    re_path(
        r'api/selection/surface/(?P<pk>\d+)/select/$',
        view=views.select_surface,
        name='surface-select'
    ),
    re_path(
        r'api/selection/surface/(?P<pk>\d+)/unselect/$',
        view=views.unselect_surface,
        name='surface-unselect'
    ),
    re_path(
        r'api/selection/topography/(?P<pk>\d+)/select/$',
        view=views.select_topography,
        name='topography-select'
    ),
    re_path(
        r'api/selection/topography/(?P<pk>\d+)/unselect/$',
        view=views.unselect_topography,
        name='topography-unselect'
    ),
    re_path(
        r'api/selection/tag/(?P<pk>\d+)/select/$',
        view=views.select_tag,
        name='tag-select'
    ),
    re_path(
        r'api/selection/tag/(?P<pk>\d+)/unselect/$',
        view=views.unselect_tag,
        name='tag-unselect'
    ),
    path(
        'api/selection/unselect-all/',
        view=views.unselect_all,
        name='unselect-all'
    ),
]

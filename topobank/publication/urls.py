from django.contrib.auth.decorators import login_required
from django.urls import re_path, path

from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'api/publication', views.PublicationViewSet, basename='publication-api')

urlpatterns = router.urls

app_name = "publication"
urlpatterns += [
    path(
        '<str:short_url>/',
        view=views.go,
        name='go'
    ),
    path(
        '<str:short_url>/download/',
        view=views.download,
        name='go-download'
    ),
    re_path(
        r'publish/(?P<pk>\d+)/$',
        view=login_required(views.SurfacePublishView.as_view()),
        name='surface-publish'
    ),
    re_path(
        r'publish/(?P<pk>\d+)/publication-rate-too-high/$',
        view=login_required(views.PublicationRateTooHighView.as_view()),
        name='surface-publication-rate-too-high'
    ),
    re_path(
        r'publish/(?P<pk>\d+)/publication-error/$',
        view=login_required(views.PublicationErrorView.as_view()),
        name='surface-publication-error'
    ),
]

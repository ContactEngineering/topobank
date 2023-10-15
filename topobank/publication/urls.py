from django.urls import path

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
    )
]

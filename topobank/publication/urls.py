from django.urls import path

from . import views

app_name = "publication"
urlpatterns = [
    path(
        '<str:short_url>/',
        view=views.go,
        name='go'
    ),
]

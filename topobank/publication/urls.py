from django.urls import path

from . import views

app_name = "publication"
urlpatterns = [
    path(
        '<uuid:ref>/',
        view=views.go,
        name='go'
    ),
]

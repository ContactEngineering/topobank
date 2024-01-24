from django.contrib.auth.decorators import login_required
from django.urls import re_path

from . import views

app_name = "plugins"
urlpatterns = [
    re_path(
        r'list/$',
        view=login_required(views.PluginListView.as_view()),
        name='plugins-list'
    ),
]

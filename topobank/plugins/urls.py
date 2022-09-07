from django.conf.urls import re_path
from django.contrib.auth.decorators import login_required


from . import views

app_name = "plugins"
urlpatterns = [
    re_path(
        regex=r'list/$',
        view=login_required(views.PluginListView.as_view()),
        name='plugins-list'
    ),
]

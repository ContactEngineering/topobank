from django.conf.urls import url
from django.contrib.auth.decorators import login_required


from . import views

app_name = "plugins"
urlpatterns = [
    url(
        regex=r'list/$',
        view=login_required(views.PluginListView.as_view()),
        name='plugins-list'
    ),
]

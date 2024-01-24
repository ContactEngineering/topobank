from django.apps import apps
from django.conf import settings
from django.views.generic import TemplateView

from topobank.organizations.models import Organization


class PluginListView(TemplateView):
    template_name = "plugins/plugins_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # only show plugins available for his user
        plugins_available = Organization.objects.get_plugins_available(self.request.user)
        context['plugin_apps'] = [apps.get_app_config(app) for app in settings.PLUGIN_APPS
                                  if app in plugins_available]

        #
        # Add context needed for tabs
        #
        context['extra_tabs'] = [
            {
                'title': "Plugins",
                'icon': "plug",
                'href': self.request.path,
                'active': True,
                'tooltip': "Installed plugins"
            }
        ]
        return context

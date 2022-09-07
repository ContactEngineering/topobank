from django.views.generic import TemplateView
from django.conf import settings
from django.apps import apps

class PluginListView(TemplateView):
    template_name = "plugins/plugins_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['plugin_apps'] = [ apps.get_app_config(app) for app in settings.PLUGIN_APPS]
        #
        # Add context needed for tabs
        #
        context['extra_tabs'] = [
            {
                'title': f"Plugins",
                'icon': "plug",
                'href': self.request.path,
                'active': True,
                'tooltip': f"Installed Plugins"
            }
        ]
        return context

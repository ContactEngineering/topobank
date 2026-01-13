from django.apps import apps
from django.conf import settings

from topobank.organizations.models import Organization


def get_user_available_plugins(user):
    """
    Get the list of plugin app configs available to the given user. This includes all
    unrestricted plugins and those restricted plugins that the user's organization has access to.
    Args:
        user: User instance
    Returns: List of available plugin app configs
    """

    organization_plugins = Organization.objects.get_plugins_available(user)

    # Get app configs for available plugins by matching module names.
    # Plugins that are not restricted are always included.
    plugin_apps = [
        app_config for app_config in apps.get_app_configs()
        if app_config.name in settings.PLUGIN_MODULES
        and (app_config.name in organization_plugins
             or not getattr(getattr(app_config, 'TopobankPluginMeta', None), 'restricted', True))
    ]

    return plugin_apps

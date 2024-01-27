import logging
import sys

from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

_log = logging.getLogger(__name__)


class PluginConfig(AppConfig):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self, 'TopobankPluginMeta'):
            raise ImproperlyConfigured("A topobank plugin config should have a TopobankPluginMeta inner class.")

        if hasattr(self.TopobankPluginMeta, 'compatibility') and not settings.TOPOBANK_PLUGINS_IGNORE_CONFLICTS:
            import pkg_resources
            try:
                pkg_resources.require(self.TopobankPluginMeta.compatibility)
            except pkg_resources.VersionConflict as e:
                _log.error("Incompatible plugins found!")
                _log.error(f"Plugin {self.name} requires you to have {e.req}, but you installed {e.dist}.")
                sys.exit(1)

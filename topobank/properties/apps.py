from django.apps import AppConfig


class PropertiesAppConfig(AppConfig):
    name = "topobank.properties"

    def ready(self):
        # make sure the signals are registered now
        import topobank.files.signals  # noqa: F401

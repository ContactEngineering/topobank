from django.apps import AppConfig


class FilesAppConfig(AppConfig):
    name = 'topobank.files'

    def ready(self):
        # make sure the signals are registered now
        # import topobank.files.signals  # noqa: F401
        pass

from django.apps import AppConfig


class PublicationAppConfig(AppConfig):
    name = 'topobank.publication'

    def ready(self):
        # make sure the signals are registered now
        import topobank.publication.signals


from django.apps import AppConfig

class ManagerAppConfig(AppConfig):
    name = 'topobank.manager'

    def ready(self):
        # make sure the signals are registered now
        import topobank.manager.signals

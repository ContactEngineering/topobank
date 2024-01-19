from django.apps import AppConfig


class UsageStatsAppConfig(AppConfig):
    name = 'topobank.usage_stats'

    def ready(self):
        from .utils import register_metrics
        register_metrics()

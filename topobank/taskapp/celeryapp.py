import os

from celery import Celery
from celery.schedules import crontab
from django.apps import AppConfig, apps
from django.conf import settings

if not settings.configured:
    # set the default Django settings module for the 'celery' program.
    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE", "topobank.settings.local"
    )  # pragma: no cover

app = Celery("topobank")


class CeleryAppConfig(AppConfig):
    name = "topobank.taskapp"
    verbose_name = "Celery Config"

    def ready(self):
        # Using a string here means the worker will not have to
        # pickle the object when using Windows.
        app.config_from_object("django.conf:settings", namespace="CELERY")
        installed_apps = [app_config.name for app_config in apps.get_app_configs()]
        app.autodiscover_tasks(lambda: installed_apps, force=True)

        #
        # I had problems using the celery signal 'on_after_configure'.
        # Also see here: https://github.com/celery/celery/issues/3589
        # Therefore I'm using an explicit configuration of the schedule instead
        # of using the decorator.
        #
        app.conf.beat_schedule = {
            "save-landing-page-statistics": {
                "task": "topobank.taskapp.tasks.save_landing_page_statistics",
                "schedule": crontab(hour="0", minute="0"),
            },
            "manager-periodic-cleanup": {
                "task": "topobank.manager.custodian.periodic_cleanup",
                "schedule": 12 * 3600,  # Twice a day
            },
            "analysis-periodic-cleanup": {
                "task": "topobank.analysis.custodian.periodic_cleanup",
                "schedule": 12 * 3600,  # Twice a day
            },
        }

import logging
import os
import traceback as tb

from celery import Celery
from celery.signals import task_failure, task_revoked, task_success
from django.apps import AppConfig, apps
from django.conf import settings
from django.utils import timezone

_log = logging.getLogger(__name__)

if not settings.configured:
    # set the default Django settings module for the 'celery' program.
    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE", "topobank.settings.local"
    )  # pragma: no cover
    _log.info("No configured. Using DJANGO_SETTINGS_MODULE='{}'".format(os.environ["DJANGO_SETTINGS_MODULE"]))

app = Celery("topobank")


class CeleryAppConfig(AppConfig):
    name = "topobank.taskapp"
    verbose_name = "Celery Config"

    def ready(self):
        # Using a string here means the worker will not have to
        # pickle the object when using Windows.
        app.config_from_object("django.conf:settings", namespace="CELERY")
        installed_apps = [app_config.name for app_config in apps.get_app_configs()]
        _log.info("Autodiscovering tasks in apps: {}".format(installed_apps))
        app.autodiscover_tasks(lambda: installed_apps, force=True)

        #
        # I had problems using the celery signal 'on_after_configure'.
        # Also see here: https://github.com/celery/celery/issues/3589
        # Therefore I'm using an explicit configuration of the schedule instead
        # of using the decorator.
        #
        app.conf.beat_schedule = {
            "manager-periodic-cleanup": {
                "task": "topobank.manager.custodian.periodic_cleanup",
                "schedule": 12 * 3600,  # Twice a day
                "options": {"queue": settings.TOPOBANK_MANAGER_QUEUE}
            },
            "analysis-periodic-cleanup": {
                "task": "topobank.analysis.custodian.periodic_cleanup",
                "schedule": 12 * 3600,  # Twice a day
                "options": {"queue": settings.TOPOBANK_MANAGER_QUEUE}
            },
        }

        # Register Celery signal handlers for automatic task state synchronization
        self._register_task_state_signals()

    def _register_task_state_signals(self):
        """Register Celery signal handlers for automatic task state synchronization."""

        @task_failure.connect(weak=False)
        def handle_task_failure(sender=None, task_id=None, exception=None,
                                traceback=None, **kwargs):
            """
            Handle task failures reported by Celery.

            This catches:
            - Worker crashes
            - Timeouts
            - Out-of-memory kills
            - Unhandled exceptions that bypass task's own error handling
            """
            try:
                instance = self._find_task_instance(task_id)
                if instance is None:
                    _log.debug(f"Task {task_id} failed but no TaskStateModel instance found")
                    return

                # Only update if not already in a terminal state
                # (task's own error handling may have already set it)
                if instance.task_state not in ['su', 'fa']:  # SUCCESS or FAILURE
                    _log.info(
                        f"Celery reported failure for {instance.__class__.__name__} "
                        f"id={instance.id}, task_id={task_id}. Updating database state."
                    )
                    instance.task_state = 'fa'  # FAILURE
                    instance.task_error = str(exception) if exception else "Task failed"
                    instance.task_traceback = traceback if traceback else ""
                    instance.task_end_time = timezone.now()
                    instance.save(update_fields=[
                        'task_state', 'task_error', 'task_traceback', 'task_end_time'
                    ])
                else:
                    _log.debug(
                        f"Task {task_id} failed in Celery but {instance.__class__.__name__} "
                        f"id={instance.id} already in terminal state: {instance.task_state}"
                    )
            except Exception as e:
                # Never let signal handler crash
                _log.error(
                    f"Error in task_failure signal handler for task {task_id}: {e}\n"
                    f"{tb.format_exc()}"
                )

        @task_revoked.connect(weak=False)
        def handle_task_revoked(sender=None, request=None, terminated=None,
                                signum=None, expired=None, **kwargs):
            """
            Handle tasks that were explicitly cancelled/revoked.

            This catches:
            - Admin cancellations via Flower or celery control
            - Tasks killed by terminate=True
            - Expired tasks (if using task_expires)
            """
            try:
                task_id = request.id if request else None
                if not task_id:
                    return

                instance = self._find_task_instance(task_id)
                if instance is None:
                    _log.debug(f"Task {task_id} revoked but no TaskStateModel instance found")
                    return

                # Only update if not already in a terminal state
                if instance.task_state not in ['su', 'fa']:  # SUCCESS or FAILURE
                    reason = "Task was cancelled"
                    if terminated:
                        reason += " (terminated)"
                    if expired:
                        reason += " (expired)"

                    _log.info(
                        f"Task revoked for {instance.__class__.__name__} "
                        f"id={instance.id}, task_id={task_id}. Reason: {reason}"
                    )
                    instance.task_state = 'fa'  # FAILURE
                    instance.task_error = reason
                    instance.task_end_time = timezone.now()
                    instance.save(update_fields=[
                        'task_state', 'task_error', 'task_end_time'
                    ])
                else:
                    _log.debug(
                        f"Task {task_id} revoked but {instance.__class__.__name__} "
                        f"id={instance.id} already in terminal state: {instance.task_state}"
                    )
            except Exception as e:
                # Never let signal handler crash
                _log.error(
                    f"Error in task_revoked signal handler for task {task_id}: {e}\n"
                    f"{tb.format_exc()}"
                )

        @task_success.connect(weak=False)
        def handle_task_success(sender=None, result=None, **kwargs):
            """
            Handle successful task completion reported by Celery.

            This is primarily for validation - if Celery reports success but
            the database shows failure, we log a warning for investigation.
            """
            try:
                # Try to get task_id from sender
                task_id = None
                if hasattr(sender, 'request') and hasattr(sender.request, 'id'):
                    task_id = sender.request.id

                if not task_id:
                    return

                instance = self._find_task_instance(task_id)
                if instance is None:
                    return

                # Log if there's a mismatch (Celery says success, DB says failure)
                if instance.task_state == 'fa':  # FAILURE
                    _log.warning(
                        f"State mismatch: Celery reports SUCCESS for "
                        f"{instance.__class__.__name__} id={instance.id}, task_id={task_id}, "
                        f"but database shows FAILURE. This may indicate an issue with "
                        f"task state reporting."
                    )
            except Exception as e:
                # Never let signal handler crash
                _log.error(
                    f"Error in task_success signal handler: {e}\n{tb.format_exc()}"
                )

    def _find_task_instance(self, task_id):
        """
        Find a TaskStateModel instance by task_id.

        Searches all models that inherit from TaskStateModel:
        - WorkflowResult (analysis results)
        - Topography (dataset measurements)
        - ZipContainer (ZIP file exports)

        Returns None if not found.
        """
        if not task_id:
            return None

        # Import here to avoid circular imports
        from topobank.analysis.models import WorkflowResult
        from topobank.manager.models import Topography
        from topobank.manager.zip_model import ZipContainer

        # Search each model type
        for model_class in [WorkflowResult, Topography, ZipContainer]:
            try:
                return model_class.objects.get(task_id=task_id)
            except model_class.DoesNotExist:
                continue
            except Exception as e:
                _log.error(
                    f"Error querying {model_class.__name__} for task_id {task_id}: {e}"
                )
                continue

        return None

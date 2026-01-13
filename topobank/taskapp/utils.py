import importlib
from typing import Optional

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from watchman.decorators import check as watchman_check

from .celeryapp import app
from .models import Dependency, TaskStateModel, Version

PENDING = "pe"
STARTED = "st"
RETRY = "re"
FAILURE = "fa"
SUCCESS = "su"
NOTRUN = "no"

TASK_STATE_CHOICES = (
    (PENDING, "pending"),
    (STARTED, "started"),
    (RETRY, "retry"),
    (FAILURE, "failure"),
    (SUCCESS, "success"),
    (NOTRUN, "not run"),
)


class ConfigurationException(Exception):
    pass


def _get_package_version_tuple(pkg_name, version_expr):
    """

    :param pkg_name: name of the package which is used in import statement
    :param version_expr: expression used to get the version from already imported module
    :return: version tuple
    """
    mod = importlib.import_module(pkg_name)

    version = eval(version_expr, {pkg_name: mod})

    version_tuple = version.split(".")

    try:
        major: int = int(version_tuple[0])
    except:  # noqa: E722
        raise ConfigurationException(
            f"Cannot determine major version of package '{pkg_name}'. "
            f"Full version string: {version}"
        )

    try:
        minor: int = int(version_tuple[1])
    except:  # noqa: E722
        raise ConfigurationException(
            "Cannot determine minor version of package '{}'. Full version string: {}",
            format(pkg_name, version),
        )

    try:
        # because of version strings like '0.51.0+0.g2c488bd.dirty'
        micro: int = int(version_tuple[2].split("+")[0])
        s = f"{version_tuple[0]}.{version_tuple[1]}.{micro}"
    except:  # noqa: E722
        micro = None
        s = f"{version_tuple[0]}.{version_tuple[1]}"

    try:
        extra: str = version[len(s) :]  # the rest of the version string
    except:  # noqa: E722
        extra = None

    return major, minor, micro, extra


@transaction.atomic(durable=True)
def get_package_version(pkg_name, version_expr):
    """
    Return version instance for currently installed version of a package.
    The function creates the entry in the dependency and version tables if
    they are missing. This serves to track versions of packages that are used
    for generating analysis results.

    Parameters
    ----------
    pkg_name : str
        name of the package which is used in import statement
    version_expr : str
        expression (Python code) used to get the version from already
        imported module

    Returns
    -------
    version : Version
        Instance of the Version class
    """
    major, minor, micro, extra = _get_package_version_tuple(pkg_name, version_expr)

    # create dependency object if it does not yet exist
    dep, created = Dependency.objects.get_or_create(import_name=pkg_name)

    # make sure the current version of the dependency is available in database
    version, created = Version.objects.get_or_create(
        dependency=dep, major=major, minor=minor, micro=micro, extra=extra
    )

    return version


def celery_worker_check():
    return {
        "celery": _celery_worker_check(),
    }


@watchman_check
def _celery_worker_check():
    """Used with watchman in order to check whether celery workers are available."""
    # See https://github.com/mwarkentin/django-watchman/issues/8
    from .celeryapp import app

    MIN_NUM_WORKERS_EXPECTED = 1
    d = app.control.broadcast(
        "ping", reply=True, timeout=0.5, limit=MIN_NUM_WORKERS_EXPECTED
    )
    return {
        "num_workers_available": len(d),
        "min_num_workers_expected": MIN_NUM_WORKERS_EXPECTED,
        "ok": len(d) >= MIN_NUM_WORKERS_EXPECTED,
    }


@app.task(bind=True)
def task_dispatch(celery_task, cls_id, obj_id, *args, **kwargs):
    ct = ContentType.objects.get_for_id(cls_id)
    try:
        obj = ct.get_object_for_this_type(id=obj_id)
        obj.run_task(celery_task, *args, **kwargs)
        # Return True so Celery knows the task completed successfully
        # This is important for tasks that do not return anything
        return True
    except ct.model_class().DoesNotExist:
        # Ignore the task if the instance no longer exists
        return None


def run_task(
    model_instance: TaskStateModel, celery_queue: Optional[str] = None, *args, **kwargs
):
    model_instance.set_pending_state(autosave=False)
    # Only submit this on_commit, once save() has finalized and everything
    # has been flushed to the database (including a possible 'pe'nding state)
    celery_kwargs = {}
    if celery_queue is not None:
        # Explicit celery queue given
        celery_kwargs["queue"] = celery_queue
    elif hasattr(model_instance, "celery_queue"):
        # Static celery queue
        celery_kwargs["queue"] = model_instance.celery_queue
    elif hasattr(model_instance, "get_celery_queue"):
        # Dynamic celery queue
        celery_kwargs["queue"] = model_instance.get_celery_queue()

    def submit_task_to_celery():
        model_instance.task_id = task_dispatch.apply_async(
            args=[
                ContentType.objects.get_for_model(model_instance).id,
                model_instance.id,
            ]
            + list(args),
            kwargs=kwargs,
            **celery_kwargs,
        ).id
        model_instance.save(update_fields=["task_id"])

    transaction.on_commit(submit_task_to_celery)

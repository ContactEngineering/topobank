"""
Historical home of the workflow tasks.

The Celery tasks live in :mod:`topobank.analysis.celery.tasks` now and keep
their ``topobank.analysis.tasks.*`` names; importing this module registers
them, which is what Celery's task autodiscovery relies on. The engine-neutral
helpers that used to sit next to them moved to
:mod:`topobank.analysis.configuration` and :mod:`topobank.analysis.utils`.
"""

from .celery.tasks import (  # noqa: F401
    DEFAULT_TASK_SOFT_TIME_LIMIT,
    DEFAULT_TASK_TIME_LIMIT,
    TASK_SOFT_TIME_LIMIT,
    TASK_TIME_LIMIT,
    _fail_parent_on_dependency_failure,
    execute_workflow,
    perform_analysis,
    prepare_dependency_tasks,
    schedule_workflow,
)
from .configuration import get_current_configuration  # noqa: F401
from .utils import current_statistics  # noqa: F401

"""
Definition of celery tasks used in TopoBank.
"""

import pydantic
from celery.app.log import TaskFormatter
from celery.signals import after_setup_task_logger
from celery.utils.log import get_task_logger

from ..usage_stats.utils import current_statistics
from ..users.models import User
from .celeryapp import app

_log = get_task_logger(__name__)


# From https://github.com/czue/celery-progress/blob/master/celery_progress/backend.py
# (MIT licensed)
class ProgressRecorder:
    class Model(pydantic.BaseModel):
        pending: bool = True
        current: float = 0.0
        total: float = 1.0
        message: str | None = None

    PROGRESS_STATE = "PROGRESS"

    def __init__(self, task):
        self._task = task
        self._total = None
        self._message = None

    def started(self, message=None):
        if message is None:
            message = self._message
        self._message = message
        total = self._total if self._total else 1
        return self.set_progress(0, total, message=message)

    def finished(self, message=None):
        if message is None:
            message = self._message
        self._message = message
        total = self._total if self._total else 1
        return self.set_progress(total, total, message=message)

    def set_progress(self, current, total, message=None):
        if message is None:
            message = self._message
        self._message = message
        self._total = total
        state = self.PROGRESS_STATE
        _log.debug(f"Task progress: {state}, {current}/{total}, {message}")
        meta = self.Model(
            pending=False,
            current=current,
            total=total,
            message=message,
        ).model_dump()
        self._task.update_state(state=state, meta=meta)
        return state, meta


@after_setup_task_logger.connect
def setup_task_logger(logger, *args, **kwargs):
    fmt = (
        "%(asctime)s - %(task_id)s - %(task_name)s - %(name)s - %(levelname)s - "
        "%(message)s"
    )
    for handler in logger.handlers:
        handler.setFormatter(TaskFormatter(fmt))


@app.task
def save_landing_page_statistics():
    from trackstats.models import Metric, Period, StatisticByDate

    _log.debug("Saving landing page statistics..")
    #
    # Number of users
    #
    from django.db.models import Q

    from topobank.users.anonymous import get_anonymous_user

    anon = get_anonymous_user()
    num_users = User.objects.filter(Q(is_active=True) & ~Q(pk=anon.pk)).count()

    StatisticByDate.objects.record(
        metric=Metric.objects.USER_COUNT, value=num_users, period=Period.DAY
    )

    #
    # Number of surfaces, topographies, analyses
    #
    # Publications should not increase these numbers
    #
    current_stats = current_statistics()

    StatisticByDate.objects.record(
        metric=Metric.objects.SURFACE_COUNT,
        value=current_stats["num_surfaces_excluding_publications"],
        period=Period.DAY,
    )
    StatisticByDate.objects.record(
        metric=Metric.objects.TOPOGRAPHY_COUNT,
        value=current_stats["num_topographies_excluding_publications"],
        period=Period.DAY,
    )
    StatisticByDate.objects.record(
        metric=Metric.objects.ANALYSIS_COUNT,
        value=current_stats["num_analyses_excluding_publications"],
        period=Period.DAY,
    )

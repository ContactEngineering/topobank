"""
Definition of celery tasks used in TopoBank.
"""

from decimal import Decimal

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
    PROGRESS_STATE = 'PROGRESS'

    def __init__(self, task):
        self.task = task

    def set_progress(self, current, total, description=""):
        percent = 0
        if total > 0:
            percent = (Decimal(current) / Decimal(total)) * Decimal(100)
            percent = float(round(percent, 2))
        state = self.PROGRESS_STATE
        meta = {
            'pending': False,
            'current': current,
            'total': total,
            'percent': percent,
            'description': description
        }
        self.task.update_state(
            state=state,
            meta=meta
        )
        return state, meta


@after_setup_task_logger.connect
def setup_task_logger(logger, *args, **kwargs):
    fmt = '%(asctime)s - %(task_id)s - %(task_name)s - %(name)s - %(levelname)s - %(message)s'
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
    from guardian.compat import get_user_model as guardian_user_model
    anon = guardian_user_model().get_anonymous()
    num_users = User.objects.filter(Q(is_active=True) & ~Q(pk=anon.pk)).count()

    StatisticByDate.objects.record(
        metric=Metric.objects.USER_COUNT,
        value=num_users,
        period=Period.DAY
    )

    #
    # Number of surfaces, topographies, analyses
    #
    # Publications should not increase these numbers
    #
    current_stats = current_statistics()

    StatisticByDate.objects.record(
        metric=Metric.objects.SURFACE_COUNT,
        value=current_stats['num_surfaces_excluding_publications'],
        period=Period.DAY
    )
    StatisticByDate.objects.record(
        metric=Metric.objects.TOPOGRAPHY_COUNT,
        value=current_stats['num_topographies_excluding_publications'],
        period=Period.DAY
    )
    StatisticByDate.objects.record(
        metric=Metric.objects.ANALYSIS_COUNT,
        value=current_stats['num_analyses_excluding_publications'],
        period=Period.DAY
    )

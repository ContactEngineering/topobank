"""
Definition of celery tasks used in TopoBank.
"""

import celery
import pydantic
from celery.utils.log import get_task_logger

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

    def __init__(self, task: celery.Task | None = None):
        self._task = task
        self._total = None
        self._message = None

    def started(self, message: str | None = None):
        if message is None:
            message = self._message
        self._message = message
        total = self._total if self._total else 1
        return self.set_progress(0, total, message=message)

    def finished(self, message: str | None = None):
        if message is None:
            message = self._message
        self._message = message
        total = self._total if self._total else 1
        return self.set_progress(total, total, message=message)

    def set_progress(self, current: float, total: float, message: str | None = None):
        if message is None:
            message = self._message
        self._message = message
        self._total = total
        state = self.PROGRESS_STATE
        # _log.debug(f"Task progress: {state}, {current}/{total}, {message}")
        meta = self.Model(
            pending=False,
            current=current,
            total=total,
            message=message,
        ).model_dump()
        if self._task and self._task.request.id:
            # Eager tasks don't have a request id (task id), and this leads to problems
            # updating the task state with the Django DB backend in testing.
            self._task.update_state(state=state, meta=meta)
        return state, meta

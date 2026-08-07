"""
Tests for the optional arguments that ``TaskStateModel.run_task`` injects.

A task worker can opt into timing and into progress reporting by declaring a
``timer`` or a ``progress_recorder`` parameter; workers that declare neither
must not be handed either. Progress reporting is what lets a client show how far
a long-running job (e.g. building a download archive) has come.
"""

import pytest

from topobank.analysis.zip_model import ResultZipContainer
from topobank.taskapp.tasks import ProgressRecorder
from topobank.testing.factories import PermissionSetFactory, UserFactory


class _FakeCeleryTask:
    """Stands in for the bound Celery task passed to ``run_task``."""

    class request:
        id = "00000000-0000-0000-0000-000000000000"

    def update_state(self, **kwargs):
        pass


def _container():
    return ResultZipContainer.objects.create(
        permissions=PermissionSetFactory(user=UserFactory(), allow="view")
    )


@pytest.mark.django_db
def test_run_task_injects_a_progress_recorder(mocker):
    """A worker declaring `progress_recorder` is handed a real recorder."""
    container = _container()
    received = {}

    def task_worker(result_ids=None, progress_recorder=None):
        received["progress_recorder"] = progress_recorder

    mocker.patch.object(container, "task_worker", task_worker)
    container.run_task(_FakeCeleryTask(), result_ids=[1])

    assert isinstance(received["progress_recorder"], ProgressRecorder)


@pytest.mark.django_db
def test_run_task_does_not_inject_into_a_worker_that_does_not_want_it(mocker):
    """A worker that declares neither optional argument is called without them."""
    container = _container()
    received = {}

    def task_worker(result_ids=None):
        received["called"] = True

    mocker.patch.object(container, "task_worker", task_worker)
    container.run_task(_FakeCeleryTask(), result_ids=[1])

    assert received["called"]
    assert container.task_state == ResultZipContainer.SUCCESS


@pytest.mark.django_db
def test_run_task_still_injects_the_timer(mocker):
    """The pre-existing `timer` injection keeps working alongside progress."""
    container = _container()
    received = {}

    def task_worker(result_ids=None, timer=None):
        received["timer"] = timer

    mocker.patch.object(container, "task_worker", task_worker)
    container.run_task(_FakeCeleryTask(), result_ids=[1])

    assert received["timer"] is not None
    # `run_task` stores what the timer recorded
    assert container.task_timer is not None


@pytest.mark.django_db
def test_run_task_injects_both_arguments_together(mocker):
    container = _container()
    received = {}

    def task_worker(result_ids=None, timer=None, progress_recorder=None):
        received["timer"] = timer
        received["progress_recorder"] = progress_recorder

    mocker.patch.object(container, "task_worker", task_worker)
    container.run_task(_FakeCeleryTask(), result_ids=[1])

    assert received["timer"] is not None
    assert isinstance(received["progress_recorder"], ProgressRecorder)

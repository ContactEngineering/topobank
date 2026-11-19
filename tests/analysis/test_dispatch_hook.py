"""`TOPOBANK_WORKFLOW_DISPATCHER`: every submit path hands the pending
`WorkflowResult` to `dispatch_workflow`, which runs the configured dispatcher
or, by default, `submit_analysis_task_to_celery`."""

from types import SimpleNamespace

import pytest

from topobank.analysis.models import WorkflowResult
from topobank.analysis.workflows import SurfaceSet
from topobank.testing.factories import SurfaceFactory, Topography2DFactory

#: What the test dispatcher below was called with, `(analysis pk, force_submit)`.
calls = []


def record(analysis, force_submit):
    calls.append((analysis.pk, force_submit))


@pytest.fixture(autouse=True)
def _reset_calls():
    calls.clear()
    yield
    calls.clear()


@pytest.fixture
def custom_dispatcher(settings):
    settings.TOPOBANK_WORKFLOW_DISPATCHER = f"{__name__}.record"


@pytest.fixture
def celery(mocker):
    """`schedule_workflow.apply_async`, as the default dispatcher calls it."""
    return mocker.patch(
        "topobank.analysis.tasks.schedule_workflow.apply_async",
        return_value=SimpleNamespace(id="11111111-2222-3333-4444-555555555555"),
    )


@pytest.fixture
def surface(user_alice):
    return SurfaceFactory(created_by=user_alice)


@pytest.fixture
def topography(surface):
    return Topography2DFactory(surface=surface)


def _pending_result(test_workflow, user, topography):
    result = WorkflowResult.objects.create(
        workflow_name=test_workflow.name,
        subject_topography=topography,
        kwargs=test_workflow.clean_kwargs(None),
        created_by=user,
        task_state=WorkflowResult.SUCCESS,
    )
    result.permissions.grant_for_user(user, "edit")
    return result


@pytest.mark.django_db
def test_default_dispatcher_submits_to_celery(
    test_workflow, user_alice, topography, celery, django_capture_on_commit_callbacks
):
    result = _pending_result(test_workflow, user_alice, topography)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        result.submit(force_submit=False)

    assert len(callbacks) == 1
    celery.assert_called_once_with(
        args=[result.id, False], queue=result.get_celery_queue()
    )
    result.refresh_from_db()
    assert str(result.task_id) == "11111111-2222-3333-4444-555555555555"
    assert result.task_state == WorkflowResult.PENDING
    assert calls == []


@pytest.mark.django_db
def test_workflow_result_submit_uses_the_dispatcher(
    test_workflow,
    user_alice,
    topography,
    celery,
    custom_dispatcher,
    django_capture_on_commit_callbacks,
):
    result = _pending_result(test_workflow, user_alice, topography)

    with django_capture_on_commit_callbacks(execute=True):
        result.submit(force_submit=False)
    with django_capture_on_commit_callbacks(execute=True):
        result.submit_again()

    # `force_submit` is forwarded as given: False from `submit()`, True from
    # `submit_again()`
    assert calls == [(result.pk, False), (result.pk, True)]
    celery.assert_not_called()
    result.refresh_from_db()
    assert result.task_state == WorkflowResult.PENDING


@pytest.mark.django_db
def test_workflow_submit_uses_the_dispatcher(
    test_workflow,
    user_alice,
    topography,
    celery,
    custom_dispatcher,
    django_capture_on_commit_callbacks,
):
    with django_capture_on_commit_callbacks(execute=True):
        result = test_workflow.submit(user_alice, topography, force_submit=True)

    assert calls == [(result.pk, True)]
    celery.assert_not_called()


@pytest.mark.django_db
def test_workflow_submit_for_surfaces_uses_the_dispatcher(
    test_workflow,
    user_alice,
    surface,
    celery,
    custom_dispatcher,
    django_capture_on_commit_callbacks,
):
    with django_capture_on_commit_callbacks(execute=True):
        result = test_workflow.submit_for_surfaces(
            user_alice, [surface], test_workflow.clean_kwargs(None)
        )

    assert result.subject_hash == SurfaceSet(surfaces=[surface.id]).subject_hash
    assert calls == [(result.pk, True)]
    celery.assert_not_called()


@pytest.mark.django_db
def test_workflow_submit_again_uses_the_dispatcher(
    test_workflow,
    user_alice,
    topography,
    celery,
    custom_dispatcher,
    django_capture_on_commit_callbacks,
):
    result = _pending_result(test_workflow, user_alice, topography)

    with django_capture_on_commit_callbacks(execute=True):
        test_workflow.submit_again(result)

    assert calls == [(result.pk, True)]
    celery.assert_not_called()


@pytest.mark.django_db
def test_dispatcher_may_delegate_to_celery(
    test_workflow,
    user_alice,
    topography,
    celery,
    settings,
    django_capture_on_commit_callbacks,
):
    settings.TOPOBANK_WORKFLOW_DISPATCHER = (
        "topobank.analysis.models.submit_analysis_task_to_celery"
    )
    result = _pending_result(test_workflow, user_alice, topography)

    with django_capture_on_commit_callbacks(execute=True):
        result.submit_again()

    celery.assert_called_once_with(
        args=[result.id, True], queue=result.get_celery_queue()
    )


@pytest.mark.parametrize(
    "path, error_id",
    [
        (None, None),
        (f"{__name__}.record", None),
        (f"{__name__}.no_such_function", "topobank.analysis.E001"),
        (f"{__name__}.calls", "topobank.analysis.E002"),
    ],
)
def test_the_system_check_reports_a_dispatcher_that_does_not_resolve(settings, path, error_id):
    from topobank.analysis.checks import check_workflow_dispatcher

    settings.TOPOBANK_WORKFLOW_DISPATCHER = path
    errors = check_workflow_dispatcher(None)
    assert [e.id for e in errors] == ([error_id] if error_id else [])

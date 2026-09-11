"""
Tests for ``topobank.analysis.store``: one ``ResultRequest``, one
``find_or_create``, and the reuse policies the callers choose.
"""

import warnings

import pytest

from topobank.analysis.models import Workflow, WorkflowResult
from topobank.analysis.registry import WorkflowNotRegisteredException
from topobank.analysis.store import Found, Reuse, find_or_create
from topobank.analysis.workflows import (
    ResultRequest,
    WorkflowDefinition,
    compute_subject_hash,
)
from topobank.testing.factories import (
    OrganizationFactory,
    SurfaceFactory,
    TagFactory,
    Topography1DFactory,
    TopographyAnalysisFactory,
    UserFactory,
)

WORKFLOW = "topobank.testing.test"


# ---------------------------------------------------------------------------
# ResultRequest
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_result_request_addresses_subjects_like_the_result_does():
    surface = SurfaceFactory()
    topo = Topography1DFactory(surface=surface)
    tag = TagFactory()

    r = ResultRequest(workflow_name=WORKFLOW, subject=topo)
    assert r.subject_type == "topography"
    assert r.subject_hash == compute_subject_hash("topography", [topo.id])

    r = ResultRequest(workflow_name=WORKFLOW, subject=surface)
    assert r.subject_type == "surface"
    assert r.subject_hash == compute_subject_hash("surface", [surface.id])

    r = ResultRequest(workflow_name=WORKFLOW, subject=tag)
    assert r.subject_type == "tag"

    r = ResultRequest(workflow_name=WORKFLOW, surfaces=[surface])
    assert r.subject_type == "surfaces"
    assert r.subject_hash == compute_subject_hash("surfaces", [surface.id])


@pytest.mark.django_db
def test_result_request_needs_exactly_one_kind_of_subject():
    surface = SurfaceFactory()
    with pytest.raises(ValueError):
        ResultRequest(workflow_name=WORKFLOW)
    with pytest.raises(ValueError):
        ResultRequest(workflow_name=WORKFLOW, subject=surface, surfaces=[surface])
    with pytest.raises(ValueError):
        ResultRequest(workflow_name=WORKFLOW, surfaces=[])
    with pytest.raises(ValueError):
        ResultRequest(workflow_name=WORKFLOW, subject="not a subject")


@pytest.mark.django_db
def test_as_surface_set_only_converts_surface_subjects():
    surface = SurfaceFactory()
    topo = Topography1DFactory(surface=surface)

    converted = ResultRequest(workflow_name=WORKFLOW, subject=surface, kwargs={"a": 2}).as_surface_set()
    assert converted.subject is None
    assert converted.surfaces == [surface]
    assert converted.kwargs == {"a": 2}
    assert converted.subject_type == "surfaces"

    unchanged = ResultRequest(workflow_name=WORKFLOW, subject=topo)
    assert unchanged.as_surface_set() is unchanged
    as_set = ResultRequest(workflow_name=WORKFLOW, surfaces=[surface])
    assert as_set.as_surface_set() is as_set


@pytest.mark.django_db
def test_workflow_definition_is_a_deprecated_result_request():
    topo = Topography1DFactory()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        definition = WorkflowDefinition(
            subject=topo, function=Workflow(name=WORKFLOW), kwargs={"a": 5}
        )
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)
    assert isinstance(definition, ResultRequest)
    assert definition.workflow_name == WORKFLOW
    assert definition.function == Workflow(name=WORKFLOW)
    assert definition.subject == topo
    assert definition.kwargs == {"a": 5}


# ---------------------------------------------------------------------------
# find_or_create
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_find_or_create_creates_a_pending_result_with_completed_kwargs(test_workflow):
    user = UserFactory()
    topo = Topography1DFactory()

    found = find_or_create(
        ResultRequest(workflow_name=WORKFLOW, subject=topo, kwargs={"a": 7}), user=user
    )

    assert isinstance(found, Found)
    assert found.created and found.needs_run
    result = found.result
    assert result.workflow_name == WORKFLOW
    assert result.subject == topo
    assert result.kwargs == {"a": 7, "b": "foo"}  # defaults filled in
    assert result.subject_hash == compute_subject_hash("topography", [topo.id])
    assert result.task_state == WorkflowResult.PENDING
    assert result.task_submission_time is not None
    assert result.created_by == user
    assert result.permissions.get_for_user(user) == "edit"


@pytest.mark.django_db
def test_find_or_create_rejects_unknown_workflows():
    topo = Topography1DFactory()
    with pytest.raises(WorkflowNotRegisteredException):
        find_or_create(ResultRequest(workflow_name="nobody.knows.this", subject=topo))


@pytest.mark.django_db
def test_find_or_create_for_a_surface_set(test_workflow):
    user = UserFactory()
    s1, s2 = SurfaceFactory(), SurfaceFactory()

    found = find_or_create(ResultRequest(workflow_name=WORKFLOW, surfaces=[s1, s2]), user=user)

    result = found.result
    assert set(result.surfaces.all()) == {s1, s2}
    assert result.subject_topography is None and result.subject_surface is None
    assert result.subject_hash == compute_subject_hash("surfaces", [s1.id, s2.id])
    # Owner defaults to the first surface's owner
    assert result.owned_by_id == s1.owned_by_id

    owner = OrganizationFactory()
    found = find_or_create(
        ResultRequest(workflow_name=WORKFLOW, surfaces=[s2]), user=user, owned_by_id=owner.id
    )
    assert found.result.owned_by_id == owner.id


@pytest.mark.django_db
@pytest.mark.parametrize(
    "state",
    [
        WorkflowResult.PENDING,
        WorkflowResult.PENDING_DEPENDENCIES,
        WorkflowResult.RETRY,
        WorkflowResult.STARTED,
        WorkflowResult.SUCCESS,
    ],
)
def test_viable_reuses_pending_running_and_successful_results(test_workflow, state):
    user = UserFactory()
    existing = TopographyAnalysisFactory(
        workflow_name=WORKFLOW, kwargs={"a": 1, "b": "foo"}, task_state=state
    )
    existing.permissions.grant_for_user(user, "view")

    found = find_or_create(
        ResultRequest(workflow_name=WORKFLOW, subject=existing.subject),
        user=user,
        reuse=Reuse.VIABLE,
        for_user=True,
    )

    assert found.result == existing
    assert not found.created and not found.needs_run


@pytest.mark.django_db
def test_viable_replaces_failed_results_but_keeps_named_ones(test_workflow):
    user = UserFactory()
    failed = TopographyAnalysisFactory(
        workflow_name=WORKFLOW, kwargs={"a": 1, "b": "foo"}, task_state=WorkflowResult.FAILURE
    )
    failed.permissions.grant_for_user(user, "view")
    topo = failed.subject
    named = TopographyAnalysisFactory(
        subject_topography=topo,
        workflow_name=WORKFLOW,
        kwargs={"a": 1, "b": "foo"},
        task_state=WorkflowResult.FAILURE,
        name="keep me",
    )
    named.permissions.grant_for_user(user, "view")

    found = find_or_create(
        ResultRequest(workflow_name=WORKFLOW, subject=topo), user=user, reuse=Reuse.VIABLE, for_user=True
    )

    assert found.created and found.needs_run
    assert not WorkflowResult.objects.filter(pk=failed.pk).exists()
    assert WorkflowResult.objects.filter(pk=named.pk).exists()


@pytest.mark.django_db
def test_viable_does_not_reuse_what_the_user_cannot_see(test_workflow):
    user = UserFactory()
    hidden = TopographyAnalysisFactory(
        workflow_name=WORKFLOW, kwargs={"a": 1, "b": "foo"}, task_state=WorkflowResult.SUCCESS
    )

    found = find_or_create(
        ResultRequest(workflow_name=WORKFLOW, subject=hidden.subject),
        user=user,
        reuse=Reuse.VIABLE,
        for_user=True,
    )
    assert found.created
    assert WorkflowResult.objects.filter(pk=hidden.pk).exists()  # not ours to delete

    # Without the user restriction the same result is reused
    found = find_or_create(
        ResultRequest(workflow_name=WORKFLOW, subject=hidden.subject), user=user, reuse=Reuse.VIABLE
    )
    assert found.result in (hidden, *WorkflowResult.objects.filter(subject_topography=hidden.subject))
    assert not found.created


@pytest.mark.django_db
def test_force_creates_anew_under_viable(test_workflow):
    user = UserFactory()
    existing = TopographyAnalysisFactory(
        workflow_name=WORKFLOW, kwargs={"a": 1, "b": "foo"}, task_state=WorkflowResult.SUCCESS
    )
    existing.permissions.grant_for_user(user, "view")

    found = find_or_create(
        ResultRequest(workflow_name=WORKFLOW, subject=existing.subject),
        user=user,
        reuse=Reuse.VIABLE,
        force=True,
        for_user=True,
    )

    assert found.created and found.needs_run
    assert not WorkflowResult.objects.filter(pk=existing.pk).exists()


@pytest.mark.django_db
def test_finished_reuses_everything_and_reports_what_still_runs(test_workflow):
    parent = TopographyAnalysisFactory()
    topo = parent.subject

    request = ResultRequest(workflow_name=WORKFLOW, subject=topo, kwargs={"a": 3})
    shared = dict(
        reuse=Reuse.FINISHED,
        permissions=parent.permissions,
        owned_by_id=parent.owned_by_id,
        metadata={"parent_workflow_result_id": parent.id},
    )

    found = find_or_create(request, user=parent.created_by, **shared)
    assert found.created and found.needs_run
    dependency = found.result
    assert dependency.permissions == parent.permissions
    assert dependency.metadata == {"parent_workflow_result_id": parent.id}
    assert dependency.owned_by_id == parent.owned_by_id

    # Still pending: reused, still has to run
    found = find_or_create(request, user=parent.created_by, **shared)
    assert found.result == dependency and not found.created and found.needs_run

    # Failed: reused and *not* run again - a failed dependency is not retried
    WorkflowResult.objects.filter(pk=dependency.pk).update(task_state=WorkflowResult.FAILURE)
    found = find_or_create(request, user=parent.created_by, **shared)
    assert found.result == dependency and not found.needs_run

    # ... unless forced
    found = find_or_create(request, user=parent.created_by, force=True, **shared)
    assert found.result == dependency and found.needs_run

    WorkflowResult.objects.filter(pk=dependency.pk).update(task_state=WorkflowResult.SUCCESS)
    found = find_or_create(request, user=parent.created_by, **shared)
    assert found.result == dependency and not found.needs_run


@pytest.mark.django_db
def test_never_always_creates_and_leaves_existing_rows_alone(test_workflow):
    user = UserFactory()
    surface = SurfaceFactory()
    request = ResultRequest(workflow_name=WORKFLOW, surfaces=[surface])

    first = find_or_create(request, user=user, reuse=Reuse.NEVER).result
    WorkflowResult.objects.filter(pk=first.pk).update(task_state=WorkflowResult.FAILURE)
    second = find_or_create(request, user=user, reuse=Reuse.NEVER).result

    assert first != second
    assert WorkflowResult.objects.filter(pk=first.pk).exists()
    assert WorkflowResult.objects.filter(subject_hash=request.subject_hash).count() == 2


@pytest.mark.django_db
def test_tag_results_are_private_to_the_user(test_workflow):
    tag = TagFactory()
    surface = SurfaceFactory()
    surface.tags.add(tag)
    alice, bob = UserFactory(), UserFactory()
    surface.permissions.grant_for_user(alice, "view")
    surface.permissions.grant_for_user(bob, "view")
    request = ResultRequest(workflow_name=WORKFLOW, subject=tag)

    theirs = find_or_create(request, user=alice, reuse=Reuse.VIABLE, for_user=True).result
    mine = find_or_create(request, user=bob, reuse=Reuse.VIABLE, for_user=True)

    assert mine.created
    assert mine.result != theirs
    assert WorkflowResult.objects.filter(pk=theirs.pk).exists()

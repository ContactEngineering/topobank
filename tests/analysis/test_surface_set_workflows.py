"""
Tests for the surface-set workflow path introduced in SD-616 (commit fdf27f2).

Covers:
- ``compute_subject_hash`` and ``SurfaceSet`` in ``topobank.analysis.workflows``
- ``WorkflowResult.compute_subject_hash`` / ``update_subject_hash`` /
  ``subject`` fallback to the ``surfaces`` M2M
- ``Workflow.submit_for_surfaces`` (creation, dedup, explicit ``owned_by_id``)
- ``WorkflowImplementation.eval_surfaces`` routing by surface count
- ``topobank.files.utils.file_storage_path`` ``uploads``/``data-lake`` split

Note: Submit tests assert DB state only — without ``transaction=True`` the
``transaction.on_commit`` hook in ``submit_analysis_task_to_celery`` is
silently skipped, so no Celery dispatch happens (mirrors ``test_submit_again``).
Coverage of ``_get_dependencies_for_surfaces`` is deferred; the existing test
workflow implementations only define ``Topography`` dependencies, so meaningful
coverage requires a new registered implementation.
"""

from types import SimpleNamespace

import pydantic
import pytest

from topobank.analysis.models import Workflow, WorkflowResult
from topobank.analysis.registry import WorkflowNotImplementedException
from topobank.analysis.workflows import SurfaceSet, compute_subject_hash
from topobank.files.utils import file_storage_path
from topobank.testing.factories import (
    SurfaceFactory,
    Topography2DFactory,
    TopographyAnalysisFactory,
)
from topobank.testing.workflows import TestImplementation

# ---------------------------------------------------------------------------
# Pure-function tests for compute_subject_hash and SurfaceSet
# ---------------------------------------------------------------------------


def test_compute_subject_hash_is_deterministic_and_order_independent():
    h1 = compute_subject_hash("surfaces", [3, 1, 2])
    h2 = compute_subject_hash("surfaces", [1, 2, 3])
    h3 = compute_subject_hash("surfaces", [3, 1, 2, 1])  # duplicate
    assert h1 == h2 == h3
    assert h1.startswith("surfaces:")


def test_compute_subject_hash_differs_for_different_id_sets():
    assert compute_subject_hash("surfaces", [1, 2]) != compute_subject_hash(
        "surfaces", [1, 2, 3]
    )
    assert compute_subject_hash("surfaces", [1]) != compute_subject_hash(
        "surfaces", [2]
    )


def test_compute_subject_hash_type_prefix_is_part_of_hash_identity():
    assert compute_subject_hash("surfaces", [1, 2]).startswith("surfaces:")
    assert compute_subject_hash("foo", [1, 2]).startswith("foo:")
    assert compute_subject_hash("surfaces", [1, 2]) != compute_subject_hash(
        "foo", [1, 2]
    )


def test_surface_set_validates_non_empty():
    with pytest.raises(pydantic.ValidationError):
        SurfaceSet(surfaces=[])


def test_surface_set_normalizes_and_exposes_subject_hash():
    s = SurfaceSet(surfaces=[5, 1, 5, 3])
    assert s.surfaces == [1, 3, 5]
    assert s.subject_hash == compute_subject_hash("surfaces", [1, 3, 5])


# ---------------------------------------------------------------------------
# WorkflowResult helpers: compute_subject_hash (static) + update_subject_hash
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_workflow_result_compute_subject_hash_static_matches_module_function():
    assert WorkflowResult.compute_subject_hash(
        "surfaces", [2, 1]
    ) == compute_subject_hash("surfaces", [1, 2])


@pytest.mark.django_db
def test_update_subject_hash_reads_m2m_and_clears_when_empty(test_analysis_function):
    s1 = SurfaceFactory()
    s2 = SurfaceFactory()
    analysis = TopographyAnalysisFactory(function=test_analysis_function)
    analysis.surfaces.set([s1, s2])

    analysis.update_subject_hash()
    analysis.refresh_from_db()
    assert analysis.subject_hash == compute_subject_hash("surfaces", [s1.id, s2.id])

    analysis.surfaces.clear()
    analysis.update_subject_hash()
    analysis.refresh_from_db()
    assert analysis.subject_hash is None


# ---------------------------------------------------------------------------
# WorkflowResult.subject fallback to the surfaces M2M
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_subject_returns_single_surface_for_one_surface_m2m(test_analysis_function):
    surface = SurfaceFactory()
    analysis = TopographyAnalysisFactory(function=test_analysis_function)
    analysis.subject_dispatch = None
    analysis.save()
    analysis.surfaces.set([surface])

    assert analysis.subject == surface


@pytest.mark.django_db
def test_subject_returns_queryset_for_multi_surface_m2m(test_analysis_function):
    s1 = SurfaceFactory()
    s2 = SurfaceFactory()
    analysis = TopographyAnalysisFactory(function=test_analysis_function)
    analysis.subject_dispatch = None
    analysis.save()
    analysis.surfaces.set([s1, s2])

    subject = analysis.subject
    # Multi-surface returns the queryset, not a single Surface.
    assert subject.count() == 2
    assert set(subject.values_list("id", flat=True)) == {s1.id, s2.id}


@pytest.mark.django_db
def test_subject_is_none_with_no_dispatch_and_no_surfaces(test_analysis_function):
    analysis = TopographyAnalysisFactory(function=test_analysis_function)
    analysis.subject_dispatch = None
    analysis.save()
    assert analysis.subject is None


# ---------------------------------------------------------------------------
# Workflow.submit_for_surfaces — DB state only (no on_commit / Celery)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_submit_for_surfaces_creates_workflow_result_with_m2m_and_hash(
    test_analysis_function, user_alice
):
    s1 = SurfaceFactory(created_by=user_alice)
    s2 = SurfaceFactory(created_by=user_alice)

    analysis = test_analysis_function.submit_for_surfaces(
        user=user_alice, surfaces=[s1, s2]
    )

    assert analysis.task_state == WorkflowResult.PENDING
    assert analysis.function == test_analysis_function
    assert analysis.subject_dispatch is None
    assert analysis.surfaces.count() == 2
    assert set(analysis.surfaces.values_list("id", flat=True)) == {s1.id, s2.id}
    assert analysis.subject_hash == SurfaceSet(
        surfaces=[s1.id, s2.id]
    ).subject_hash
    assert analysis.kwargs == test_analysis_function.get_default_kwargs()
    assert analysis.created_by == user_alice
    assert analysis.owned_by_id == s1.owned_by_id


@pytest.mark.django_db
def test_submit_for_surfaces_dedups_and_force_resubmits(
    test_analysis_function, user_alice
):
    s1 = SurfaceFactory(created_by=user_alice)
    s2 = SurfaceFactory(created_by=user_alice)

    first = test_analysis_function.submit_for_surfaces(
        user=user_alice, surfaces=[s1, s2]
    )
    second = test_analysis_function.submit_for_surfaces(
        user=user_alice, surfaces=[s1, s2]
    )
    assert second.id == first.id

    forced = test_analysis_function.submit_for_surfaces(
        user=user_alice, surfaces=[s1, s2], force_submit=True
    )
    assert forced.id != first.id
    assert forced.subject_hash == first.subject_hash


@pytest.mark.django_db
def test_submit_for_surfaces_uses_explicit_owned_by_id(
    test_analysis_function, user_alice
):
    s1 = SurfaceFactory(created_by=user_alice)
    s2 = SurfaceFactory(created_by=user_alice)
    # Pull a different organization id by creating a surface under a different user.
    other = SurfaceFactory()
    explicit_owner_id = other.owned_by_id

    analysis = test_analysis_function.submit_for_surfaces(
        user=user_alice,
        surfaces=[s1, s2],
        owned_by_id=explicit_owner_id,
    )
    assert analysis.owned_by_id == explicit_owner_id


# ---------------------------------------------------------------------------
# WorkflowImplementation.eval_surfaces routing
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_eval_surfaces_single_surface_uses_surface_implementation(
    test_analysis_function,
):
    surface = SurfaceFactory()
    Topography2DFactory(surface=surface)
    analysis = TopographyAnalysisFactory(function=test_analysis_function)
    analysis.subject_dispatch = None
    analysis.save()
    analysis.folder.remove_files()
    analysis.surfaces.set([surface])

    analysis.eval_self()

    # surface_implementation builds this comment string from default kwargs.
    assert analysis.result["comment"] == "a is 1 and b is foo"
    assert "surface" in analysis.result["name"]


@pytest.mark.django_db
def test_eval_surfaces_multi_surface_routes_to_tag_implementation(
    test_analysis_function, mocker
):
    s1 = SurfaceFactory()
    s2 = SurfaceFactory()
    analysis = TopographyAnalysisFactory(function=test_analysis_function)
    analysis.subject_dispatch = None
    analysis.save()
    analysis.surfaces.set([s1, s2])

    # Patch tag_implementation to confirm routing without depending on the body
    # (which assumes ``analysis.subject`` is a Tag — the surface-set path
    # currently exposes a queryset for multi-surface analyses).
    mock_tag = mocker.patch.object(
        TestImplementation, "tag_implementation", return_value=None
    )

    analysis.eval_self()

    mock_tag.assert_called_once()


@pytest.mark.django_db
def test_eval_surfaces_falls_back_to_topography_when_no_surface_impl():
    function = Workflow.objects.get(name="topobank.testing.topography_only_test")
    surface = SurfaceFactory()
    Topography2DFactory(surface=surface)
    analysis = TopographyAnalysisFactory(function=function)
    analysis.subject_dispatch = None
    analysis.save()
    analysis.folder.remove_files()
    analysis.surfaces.set([surface])

    analysis.eval_self()

    # topography_implementation comment uses the parameters directly.
    assert (
        analysis.result["comment"]
        == "Arguments: a is 1 and b is foo"
    )


@pytest.mark.django_db
def test_eval_surfaces_raises_when_multi_surface_lacks_tag_impl():
    function = Workflow.objects.get(name="topobank.testing.topography_only_test")
    s1 = SurfaceFactory()
    s2 = SurfaceFactory()
    analysis = TopographyAnalysisFactory(function=function)
    analysis.subject_dispatch = None
    analysis.save()
    analysis.surfaces.set([s1, s2])

    with pytest.raises(WorkflowNotImplementedException):
        analysis.eval_self()


@pytest.mark.django_db
def test_eval_surfaces_raises_value_error_when_no_surfaces(test_analysis_function):
    analysis = TopographyAnalysisFactory(function=test_analysis_function)
    runner = test_analysis_function.implementation(**analysis.kwargs)
    with pytest.raises(ValueError, match="No surfaces in analysis"):
        runner.eval_surfaces(analysis)


# ---------------------------------------------------------------------------
# file_storage_path uploads/data-lake split
# ---------------------------------------------------------------------------


def _stub_manifest(pk, kind):
    return SimpleNamespace(pk=pk, id=pk, kind=kind)


def test_file_storage_path_uses_uploads_prefix_for_raw_kind():
    assert (
        file_storage_path(_stub_manifest(42, "raw"), "scan.txt")
        == "uploads/42/scan.txt"
    )


@pytest.mark.parametrize("kind", ["der", "N/A"])
def test_file_storage_path_uses_data_lake_for_non_raw_kinds(kind):
    assert (
        file_storage_path(_stub_manifest(42, kind), "result.json")
        == "data-lake/42/result.json"
    )


def test_file_storage_path_raises_for_unsaved_instance():
    with pytest.raises(RuntimeError):
        file_storage_path(_stub_manifest(None, "raw"), "x.txt")

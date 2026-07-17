"""
Tests for issue #1343: the check-then-create dedup in submit /
submit_for_surfaces must be serialized so concurrent identical submissions do
not create duplicate WorkflowResults.
"""

import threading

import pytest
from django.db import connection

from topobank.analysis.models import WorkflowResult
from topobank.supplib.db import _advisory_lock_key, advisory_lock
from topobank.testing.factories import SurfaceFactory


def test_advisory_lock_key_is_deterministic_and_in_bigint_range():
    a = _advisory_lock_key("workflow-submit", "wf", "surfaces:abc", "{}")
    b = _advisory_lock_key("workflow-submit", "wf", "surfaces:abc", "{}")
    c = _advisory_lock_key("workflow-submit", "wf", "surfaces:xyz", "{}")
    assert a == b
    assert a != c
    assert -(2**63) <= a < 2**63


@pytest.mark.django_db
def test_advisory_lock_is_a_noop_context_manager():
    # Simply exercising the context manager must not raise (postgres executes
    # the lock; other backends no-op).
    with advisory_lock("test", 1, 2):
        pass


@pytest.mark.django_db
def test_submit_for_surfaces_is_idempotent(test_workflow, user_alice):
    """Regression guard that wrapping the dedup in a lock did not break the
    sequential dedup behaviour."""
    s1 = SurfaceFactory(created_by=user_alice)
    first = test_workflow.submit_for_surfaces(user=user_alice, surfaces=[s1])
    second = test_workflow.submit_for_surfaces(user=user_alice, surfaces=[s1])
    assert first.id == second.id
    assert WorkflowResult.objects.filter(subject_hash=first.subject_hash).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_submit_for_surfaces_creates_single_result(
    test_workflow, user_alice
):
    """Two threads submitting the same surface set concurrently must end up
    with exactly one WorkflowResult (the advisory lock serializes them)."""
    if connection.vendor != "postgresql":
        pytest.skip("advisory locks require PostgreSQL")

    s1 = SurfaceFactory(created_by=user_alice)
    surfaces = [s1]

    barrier = threading.Barrier(2)
    results = []
    errors = []

    def worker():
        try:
            barrier.wait(timeout=10)
            wr = test_workflow.submit_for_surfaces(user=user_alice, surfaces=surfaces)
            results.append(wr.id)
        except Exception as exc:  # pragma: no cover - surfaced via assertion
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, errors
    assert len(results) == 2
    # Both submissions resolve to a single stored result.
    assert (
        WorkflowResult.objects.filter(
            workflow_name=test_workflow.name
        ).count()
        == 1
    )
    assert results[0] == results[1]

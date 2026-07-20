"""
Tests for issue #1344: get_current_configuration must not create duplicate
Configuration rows under concurrency, and must never expose a Configuration
with an empty versions set.
"""

import threading

import pytest
from django.db import connection

from topobank.analysis.tasks import get_current_configuration
from topobank.taskapp.models import Configuration


@pytest.mark.django_db
def test_get_current_configuration_reuses_existing():
    c1 = get_current_configuration()
    c2 = get_current_configuration()
    assert c1.id == c2.id
    assert Configuration.objects.count() == 1
    # The stored configuration always carries its versions.
    assert c1.versions.count() > 0


@pytest.mark.django_db(transaction=True)
def test_concurrent_get_current_configuration_creates_single_row():
    if connection.vendor != "postgresql":
        pytest.skip("advisory locks require PostgreSQL")

    barrier = threading.Barrier(4)
    ids = []
    errors = []

    def worker():
        try:
            barrier.wait(timeout=10)
            ids.append(get_current_configuration().id)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, errors
    assert Configuration.objects.count() == 1
    assert len(set(ids)) == 1

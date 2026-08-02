"""Duplicate `Version` rows must be impossible, and survivable if present.

A clean release string such as "1.70.0" parses to ``extra=None``, and pre-1.70
releases also leave ``micro=None``. The old ``unique_together`` therefore
covered columns that are NULL in the common case, and PostgreSQL treats NULLs
as distinct in a UNIQUE constraint -- so nothing stopped two concurrent
``get_or_create()`` calls from inserting the same version twice. Once that
happened, the ``get()`` inside ``get_or_create()`` raised
``MultipleObjectsReturned`` and every analysis failed.
"""

import threading

import pytest
from django.db import IntegrityError, connection, transaction

from topobank.taskapp.models import Dependency, Version
from topobank.taskapp.utils import get_package_version


@pytest.mark.django_db
@pytest.mark.parametrize(
    "micro,extra",
    [
        (None, None),  # e.g. "1.70"
        (0, None),  # e.g. "1.70.0" -- the common release case
        (None, "rc1"),
        (0, "rc1"),
    ],
)
def test_duplicate_version_rejected_including_null_columns(micro, extra):
    dep = Dependency.objects.create(import_name="somepackage")
    Version.objects.create(dependency=dep, major=1, minor=70, micro=micro, extra=extra)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Version.objects.create(
                dependency=dep, major=1, minor=70, micro=micro, extra=extra
            )


@pytest.mark.django_db
def test_get_package_version_survives_preexisting_duplicates():
    # Simulate a database written before the constraint was fixed by inserting
    # a duplicate behind the ORM's back.
    version = get_package_version("numpy", repr("1.70.0"))
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO taskapp_version (dependency_id, major, minor, micro, extra) "
            "VALUES (%s, %s, %s, %s, %s)",
            [version.dependency_id, 1, 70, 0, None],
        )

    assert (
        Version.objects.filter(dependency=version.dependency, major=1, minor=70).count()
        == 2
    )

    # Must not raise MultipleObjectsReturned, and must settle on the older row.
    assert get_package_version("numpy", repr("1.70.0")).id == version.id


@pytest.mark.django_db(transaction=True)
def test_concurrent_get_package_version_creates_single_row():
    if connection.vendor != "postgresql":
        pytest.skip("relies on PostgreSQL constraint semantics")

    barrier = threading.Barrier(4)
    errors = []

    def worker():
        try:
            barrier.wait(timeout=10)
            get_package_version("numpy", repr("9.9.9"))
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, errors
    assert Version.objects.filter(major=9, minor=9, micro=9).count() == 1

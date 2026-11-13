"""
Files that the database refers to but storage no longer has are reported to
the site admins, and reading them raises MissingFileError.
"""

import pytest
from django.core import mail
from django.core.cache import cache
from django.core.files.storage import default_storage

from topobank.files.missing import MissingFileError
from topobank.testing.factories import (
    ManifestFactory,
    SurfaceFactory,
    Topography2DFactory,
)

ADMINS = [("Admin", "admin@example.com")]


@pytest.fixture(autouse=True)
def admins(settings):
    settings.ADMINS = ADMINS
    cache.clear()  # forget which files were reported already
    yield
    cache.clear()


def _lose(manifest):
    """Delete the manifest's file from storage behind the database's back."""
    default_storage.delete(manifest.file.name)
    assert not default_storage.exists(manifest.file.name)


@pytest.fixture
def lost_manifest(db):
    manifest = ManifestFactory(filename="10x10.txt")
    _lose(manifest)
    return manifest


@pytest.mark.django_db
@pytest.mark.parametrize(
    "access",
    [
        lambda m: m.open("rb"),
        lambda m: m.read(),
        lambda m: m.deepcopy(),
    ],
    ids=["open", "read", "deepcopy"],
)
def test_reading_missing_file_raises_and_emails_admins(lost_manifest, access):
    with pytest.raises(MissingFileError) as excinfo:
        access(lost_manifest)

    # Callers that handle FileNotFoundError keep working
    assert isinstance(excinfo.value, FileNotFoundError)
    assert excinfo.value.storage_name == lost_manifest.file.name

    (email,) = mail.outbox
    assert email.to == ["admin@example.com"]
    assert f"manifest {lost_manifest.pk}" in email.subject
    assert lost_manifest.file.name in email.body


@pytest.mark.django_db
def test_missing_file_is_reported_once_per_interval(lost_manifest, settings):
    for _ in range(3):
        with pytest.raises(MissingFileError):
            lost_manifest.read()
    assert len(mail.outbox) == 1

    # Once the interval has passed, it is reported again
    cache.clear()
    with pytest.raises(MissingFileError):
        lost_manifest.read()
    assert len(mail.outbox) == 2


@pytest.mark.django_db
def test_unavailable_cache_does_not_suppress_report(lost_manifest, monkeypatch):
    # django-redis with IGNORE_EXCEPTIONS returns None when redis is down
    monkeypatch.setattr("topobank.files.missing.cache.add", lambda *a, **kw: None)
    with pytest.raises(MissingFileError):
        lost_manifest.read()
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_failing_report_does_not_hide_the_error(lost_manifest, monkeypatch):
    def broken_mail(*args, **kwargs):
        raise RuntimeError("mail server exploded")

    monkeypatch.setattr("topobank.files.missing.mail_admins", broken_mail)
    with pytest.raises(MissingFileError):
        lost_manifest.read()


@pytest.mark.django_db
def test_existing_file_is_not_reported():
    manifest = ManifestFactory(filename="10x10.txt")
    assert manifest.read()
    assert mail.outbox == []


@pytest.mark.django_db
def test_reading_measurement_with_missing_datafile_names_the_measurement(user_alice):
    topography = Topography2DFactory(surface=SurfaceFactory(created_by=user_alice))
    _lose(topography.datafile)
    if topography.squeezed_datafile is not None:
        _lose(topography.squeezed_datafile)

    with pytest.raises(MissingFileError):
        topography.read()

    (email,) = mail.outbox
    assert f"Measurement {topography.pk}" in email.body
    assert f"dataset {topography.surface_id}" in email.body


@pytest.mark.django_db
def test_missing_file_error_survives_pickling(lost_manifest):
    # Task failures cross Celery and cache boundaries, which pickle exceptions
    import pickle

    with pytest.raises(MissingFileError) as excinfo:
        lost_manifest.read()

    restored = pickle.loads(pickle.dumps(excinfo.value))

    assert isinstance(restored, MissingFileError)
    assert isinstance(restored, FileNotFoundError)
    assert str(restored) == str(excinfo.value)
    assert restored.manifest_id == lost_manifest.pk
    assert restored.storage_name == lost_manifest.file.name


def test_missing_file_error_can_be_rebuilt_from_its_message():
    exc = MissingFileError("File 'x' of manifest 3 does not exist in storage")

    rebuilt = type(exc)(*exc.args)

    assert str(rebuilt) == str(exc)
    assert rebuilt.manifest_id is None

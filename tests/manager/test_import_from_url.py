"""
Tests for importing a dataset from another instance
(``topobank.manager.tasks.import_container_from_url``).

The remote describes how to obtain the container: a publication with an archived
container advertises it as 'download_url' and it can simply be fetched, while
otherwise the remote has to assemble one first, which is what
'async_download_url' is for. These tests drive both branches against a real
container, without touching the network.
"""

import tempfile

import pytest

from topobank.manager.export_zip import export_container_zip
from topobank.manager.models import Surface
from topobank.manager.tasks import import_container_from_url
from topobank.testing.factories import SurfaceFactory, Topography1DFactory, UserFactory

REMOTE_URL = "https://example.org/go/abcde"
ARCHIVED_URL = "https://example.org/go/abcde/download/"
ASYNC_URL = "https://example.org/manager/v2/download-surface/1/"
CONTAINER_FILE_URL = "https://example.org/media/container.zip"


class _Response:
    def __init__(self, json_data=None, content=None):
        self._json = json_data
        self.content = content

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


class FakeSession:
    """Stands in for a `requests.Session` talking to a remote instance."""

    def __init__(self, metadata, container_bytes):
        self.metadata = metadata
        self.container_bytes = container_bytes
        self.gets = []
        self.posts = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, headers=None):
        self.gets.append(url)
        if url == REMOTE_URL:
            return _Response(json_data=self.metadata)
        if url in (ARCHIVED_URL, CONTAINER_FILE_URL):
            return _Response(content=self.container_bytes)
        if url.endswith("/zip-container/1/"):
            return _Response(
                json_data={
                    "task_state": "su",
                    "manifest": {"file": CONTAINER_FILE_URL},
                }
            )
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url):
        self.posts.append(url)
        return _Response(json_data={"url": "https://example.org/zip-container/1/"})


@pytest.fixture
def container_bytes(db):
    """A real container, so the import path is genuinely exercised."""
    surface = SurfaceFactory(created_by=UserFactory(), name="Remote dataset")
    Topography1DFactory(surface=surface)
    with tempfile.NamedTemporaryFile(mode="wb", delete=False) as outfile:
        export_container_zip(outfile, [surface])
        path = outfile.name
    with open(path, "rb") as f:
        return f.read()


def _run(mocker, metadata, container_bytes):
    session = FakeSession(metadata, container_bytes)
    mocker.patch("topobank.manager.tasks.requests.Session", return_value=session)
    user = UserFactory()
    surface = import_container_from_url(user, REMOTE_URL)
    return session, surface


@pytest.mark.django_db
def test_prefers_the_archived_container(mocker, container_bytes):
    """With an archived container, a plain GET is enough."""
    session, surface = _run(
        mocker,
        {"download_url": ARCHIVED_URL, "async_download_url": ASYNC_URL},
        container_bytes,
    )

    assert isinstance(surface, Surface)
    assert surface.name == "Remote dataset"
    # The archived file was fetched and the remote was never asked to build one
    assert ARCHIVED_URL in session.gets
    assert session.posts == []


@pytest.mark.django_db
def test_falls_back_to_asking_the_remote_to_build_one(mocker, container_bytes):
    """Without an archived container, the remote assembles one first."""
    session, surface = _run(
        mocker,
        {"download_url": None, "async_download_url": ASYNC_URL},
        container_bytes,
    )

    assert isinstance(surface, Surface)
    assert surface.name == "Remote dataset"
    assert session.posts == [ASYNC_URL]
    assert CONTAINER_FILE_URL in session.gets


@pytest.mark.django_db
def test_falls_back_when_the_key_is_absent(mocker, container_bytes):
    """An older remote advertises no 'download_url' at all."""
    session, surface = _run(
        mocker, {"async_download_url": ASYNC_URL}, container_bytes
    )

    assert isinstance(surface, Surface)
    assert session.posts == [ASYNC_URL]


@pytest.mark.django_db
def test_reports_a_remote_that_offers_no_download(mocker, container_bytes):
    with pytest.raises(KeyError):
        _run(mocker, {"short_url": "abcde"}, container_bytes)

"""
Some helper functions
"""

import datetime
import json
import logging
import os
from dataclasses import dataclass
from numbers import Number
from operator import itemgetter
from typing import Union

import numpy as np
from django.test import SimpleTestCase
from django.utils import formats

from topobank.files.models import ManifestSet
from topobank.manager.models import Surface, Tag, Measurement

_log = logging.getLogger(__name__)

DEFAULT_DEBUG_HTML_FILENAME = "/tmp/response.html"


def assert_in_content(response, x):
    """Check whether x is in the content of given response"""

    if isinstance(x, bytes):
        in_content = x in response.content
    else:
        if isinstance(x, datetime.date):
            x = formats.date_format(x)
        else:
            x = str(x)
        in_content = bytes(x, encoding="utf-8") in response.content

    if not in_content:
        export_response_as_html(response)  # for debugging

    assert in_content, (
        f"Cannot find '{x}' in this content:\n{response.content}.\n\n"
        + f"See file://{DEFAULT_DEBUG_HTML_FILENAME} in order to view the output."
    )


def assert_not_in_content(response, x):
    """Check whether x is NOT in the content of given response"""

    if isinstance(x, datetime.date):
        representation = formats.date_format(x)
    else:
        representation = str(x)

    in_content = bytes(representation, encoding="utf-8") in response.content

    if in_content:
        export_response_as_html(response)  # for debugging

    assert not in_content, (
        f"Unexpectedly, there is '{representation}' in this content:"
        f"\n{response.content}. \n\n"
        f"See file://{DEFAULT_DEBUG_HTML_FILENAME} in order to view the output."
    )


def assert_no_form_errors(response):
    """Asserts that there is no more form, and if there is, show errors in form"""
    assert ("form" not in response.context) or (
        len(response.context["form"].errors) == 0
    ), "Form is still in context, with errors: {}".format(
        response.context["form"].errors
    )


def assert_form_error(response, error_msg_fragment, field_name=None):
    """Asserts that there is an error in form.

    Parameters
    ----------
    response: HTTPResponse object
    error_msg_fragment: str
        Substring which should be included in the error message.
    field_name: str, optional
        Name of field for which the error is expected to occur.
        If a general error message (not bound to a field) is meant,
        use `None`.

    Returns
    -------
    None

    Raises
    ------
    AssertionError
        If forms hasn't errors or not for the field as expected or the substring was
        not included.
    """
    assert ("form" in response.context) and (
        len(response.context["form"].errors) > 0
    ), "Form is expected to show errors, but there is no error."

    if not field_name:
        field_name = "__all__"

    assert (
        field_name in response.context["form"].errors
    ), "Form shows errors, but not {} which is expected. Errors: {}".format(
        (
            "independent from a special field"
            if field_name == "__all__"
            else f"for field '{field_name}'"
        ),
        response.context["form"].errors,
    )

    errors = response.context["form"].errors[field_name]

    assert any((error_msg_fragment in err) for err in errors), (
        f"Form has errors as expected, but no error contains the given error message "
        f"fragment '{error_msg_fragment}'. Instead: {errors}"
    )


# abbreviation for use with pytest
assert_redirects = SimpleTestCase().assertRedirects


def export_response_as_html(response, fname="/tmp/response.html"):  # pragma: no cover
    """
    Helper function which can be used for debugging.

    :param response: HTTPResponse
    :param fname: name of HTML output file
    """
    f = open(fname, mode="w")

    f.write(response.content.decode("utf-8").replace("\\n", "\n"))
    f.close()


def ordereddicts_to_dicts(input_ordered_dict, sorted_by="id"):
    """Convert an ordered dict to a list of dicts, also sorted."""
    result = json.loads(json.dumps(input_ordered_dict))
    if sorted_by is not None:
        result = sorted(result, key=itemgetter(sorted_by))
    return result


class AssertEqualIgnoreValue:
    pass


ASSERT_EQUAL_IGNORE_VALUE = AssertEqualIgnoreValue()


def assert_equal(a, b, key=None, ignore_keys=set(), rtol=1e-07, atol=0):
    if isinstance(a, AssertEqualIgnoreValue) or isinstance(b, AssertEqualIgnoreValue):
        return
    elif (a is None and b is not None) or (a is not None and b is None):
        raise AssertionError(f"The values key '{key}' differ: {a} != {b}")
    elif isinstance(a, dict) and isinstance(b, dict):
        assert_dict_equal(a, b, ignore_keys=ignore_keys, rtol=rtol, atol=atol)
    elif isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        np.testing.assert_allclose(
            a,
            b,
            rtol=rtol,
            atol=atol,
            err_msg=f"The values of key '{key}' differ: {a} != {b}",
        )
    elif isinstance(a, list):
        assert_dicts_equal(a, b, key=key, ignore_keys=ignore_keys, rtol=rtol, atol=atol)
    elif isinstance(a, Number) or isinstance(b, Number):
        np.testing.assert_allclose(
            a,
            b,
            rtol=rtol,
            atol=atol,
            err_msg=f"The values of key '{key}' differ: {a} != {b}",
        )
    else:
        assert a == b, f"The values key '{key}' differ: {a} != {b}"


def drf_isoformat(dt):
    """Format a datetime the same way DRF does (Z for UTC instead of +00:00)."""
    s = dt.astimezone(datetime.timezone.utc).isoformat()
    return s.replace('+00:00', 'Z')


def assert_dict_equal(a, b, ignore_keys=set(), rtol=1e-07, atol=0):
    keys_a = set(a.keys()) - set(ignore_keys)
    keys_b = set(b.keys()) - set(ignore_keys)

    assert (
        keys_a == keys_b
    ), f"Present in a but not b: {keys_a - keys_b}, present in b but not a: {keys_b - keys_a}"
    for key in keys_a:
        assert_equal(
            a[key], b[key], key=key, ignore_keys=ignore_keys, rtol=rtol, atol=atol
        )


def assert_dicts_equal(a, b, key=None, ignore_keys=set(), rtol=1e-07, atol=0):
    for x, y in zip(a, b):
        assert_equal(x, y, key=key, ignore_keys=ignore_keys, rtol=rtol, atol=atol)


###############################################################################
# Helpers for doing tests
###############################################################################


@dataclass(frozen=True)
class FakeTopographyModel:
    """This model is used to create a Measurement for being passed to analysis functions."""

    t: Measurement
    name: str = "mytopo"
    is_periodic: bool = False

    def topography(self):
        """Return low level topography."""
        return self.t


class AnalysisResultMock:
    subject: Union[Tag, Surface, Measurement] = None
    folder: ManifestSet = None

    def __init__(self, subject: Union[Tag, Surface, Measurement], folder: ManifestSet = None):
        self.subject = subject
        self.folder = folder
        if self.folder is None and hasattr(self.subject, "permissions"):
            self.folder = ManifestSet.objects.create(permissions=self.subject.permissions)


class DummyProgressRecorder:
    def set_progress(self, a, nsteps):
        """Do nothing."""
        pass  # dummy


def copy_folder(folder: ManifestSet, filepath: str):
    """Copy the folder to disk."""
    os.makedirs(filepath, exist_ok=True)
    for file in folder.get_files():
        open(f"{filepath}/{file.filename}", "wb").write(file.file.read())


def assert_file_equal(folder: ManifestSet, filepath: str, filename: str):
    data1 = folder.find_file(filename).read()
    data2 = open(f"{filepath}/{filename}", "rb").read()
    assert data1 == data2


def download_zip_container(client, url, capture_on_commit_callbacks):
    """
    Run the asynchronous download flow and return the bytes of the archive.

    ZIP containers are built by a Celery task, so a client POSTs to `url`, waits
    for the task to finish and then downloads the finished file. In tests,
    Celery runs eagerly, but the task is dispatched in an on-commit hook, hence
    the need for `capture_on_commit_callbacks`.

    Parameters
    ----------
    client : django.test.Client or rest_framework.test.APIClient
        Client used for the request.
    url : str
        The route that creates the container, e.g. the one reversed from
        'manager:surface-download-v2'.
    capture_on_commit_callbacks : callable
        The `django_capture_on_commit_callbacks` pytest-django fixture.

    Returns
    -------
    bytes
        The archive.
    """
    from topobank.manager.zip_model import ZipContainer

    with capture_on_commit_callbacks(execute=True):
        response = client.post(url)
    assert response.status_code == 200, response.content

    container = ZipContainer.objects.get(id=response.json()["id"])
    assert container.get_task_state() == ZipContainer.SUCCESS, container.task_error
    assert container.manifest is not None
    return container.manifest.read()


def import_container_from_url_or_skip(user, url, tag=None):
    """
    Import a container from a remote instance, skipping the test if that is not
    possible.

    Tests that exercise the cross-instance import run against a live remote, so
    they are skipped when it cannot be reached. They are also skipped when the
    remote does not advertise an `async_download_url`: containers are built
    asynchronously and older deployments still offer only the synchronous
    `download_url` that this stack no longer speaks.

    Parameters
    ----------
    user : `topobank.users.models.User`
        The user who imports the container.
    url : str
        URL of the published dataset on the remote instance.
    tag : Tag, optional
        Tag to associate with the imported container.

    Returns
    -------
    Surface
        The imported dataset.
    """
    import urllib.error

    import pytest
    import requests

    from topobank.manager.tasks import import_container_from_url

    try:
        return import_container_from_url(user, url, tag=tag)
    except KeyError as exc:
        pytest.skip(
            f"The instance at {url} does not offer an asynchronous download "
            f"({exc}); it is probably running an older version."
        )
    except (
        urllib.error.URLError,
        OSError,
        requests.exceptions.RequestException,
    ) as exc:  # pragma: no cover - network
        pytest.skip(f"Could not download container from {url}: {exc}")

"""
Some helper functions
"""

import datetime
import json
import logging
from dataclasses import dataclass
from operator import itemgetter
from typing import Union

import numpy as np
import requests
from django.conf import settings
from django.test import SimpleTestCase
from django.utils import formats
from rest_framework.reverse import reverse

from topobank.files.models import Folder
from topobank.manager.models import Surface, Tag, Topography

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


def upload_file(api_client, upload_instructions, fn):
    url = upload_instructions["url"]
    method = upload_instructions["method"]
    _log.debug(f"Upload to url: {url}, method: {method}")
    with open(fn, mode="rb") as fp:
        if method == "POST":
            if settings.USE_S3_STORAGE:
                # We need to use `requests` as the upload is directly to S3, not to the
                # Django app
                response = requests.post(
                    url,
                    data={**upload_instructions["fields"]},
                    files={"file": fp},
                )
            else:
                response = api_client.post(
                    url,
                    {**upload_instructions["fields"], "file": fp},
                    format="multipart",
                )
            assert response.status_code == 204, response.content  # Created
        elif method == "PUT":
            if settings.USE_S3_STORAGE:
                # We need to use `requests` as the upload is directly to S3, not to the
                # Django app
                response = requests.put(
                    url, data=fp, headers={"Content-Type": "binary/octet-stream"}
                )
            else:
                raise RuntimeError("PUT uploads not supported without S3")
            assert response.status_code == 200, response.content  # OK
        else:
            raise RuntimeError(f"Unknown upload method {method}")


def upload_topography_file(
    fn,
    surface_id,
    api_client,
    django_capture_on_commit_callbacks,
    final_task_state="su",
    **kwargs,
):
    # create new topography (and request file upload location)
    _log.debug(f"Uploading file '{fn}'...")
    name = fn.split("/")[-1]
    response = api_client.post(
        reverse("manager:topography-api-list"),
        {
            "surface": reverse(
                "manager:surface-api-detail", kwargs=dict(pk=surface_id)
            ),
            "name": name,
            **kwargs,
        },
    )
    assert response.status_code == 201, response.content  # Created
    topography_id = response.data["id"]

    # The POST request above informs us how to upload the file
    upload_instructions = response.data["datafile"]["upload_instructions"]
    upload_file(api_client, upload_instructions, fn)

    # We need to execute on commit actions, because this is where the refresh_cache task
    # is triggered
    with django_capture_on_commit_callbacks(execute=True):
        # Get info on file (this will trigger the inspection). In the production
        # instance, the first GET triggers a background (Celery) task and always returns
        # a 'pe'nding state. In this testing environment, this is run immediately after
        # the `save` but not yet reflected in the returned dictionary.
        response = api_client.get(
            reverse("manager:topography-api-detail", kwargs=dict(pk=topography_id))
        )
        assert response.status_code == 200, response.content
        assert response.data["task_state"] == "pe", response.data["task_state"]
        # We need to close the commit capture here because the file inspection runs on
        # commit

    with django_capture_on_commit_callbacks(execute=True):
        # Get info on file again, this should not report a successful file inspection.
        response = api_client.get(
            reverse("manager:topography-api-detail", kwargs=dict(pk=topography_id))
        )
        assert response.status_code == 200, response.content
        assert response.data["task_state"] == final_task_state, response.data[
            "task_state"
        ]

    return response


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


def assert_equal(a, b, key=None, rtol=1e-07, atol=0):
    if isinstance(a, dict):
        assert_dict_equal(a, b, key=key, rtol=rtol, atol=atol)
    elif isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        np.testing.assert_allclose(
            a,
            b,
            rtol=rtol,
            atol=atol,
            err_msg=f"The values of key '{key}' differ: {a} != {b}",
        )
    elif isinstance(a, list):
        assert_dicts_equal(a, b, key=key, rtol=rtol, atol=atol)
    else:
        assert a == b, f"The values key '{key}' differ: {a} != {b}"


def assert_dict_equal(a, b, key=None, rtol=1e-07, atol=0):
    keys_a = set(a.keys())
    keys_b = set(b.keys())

    assert (
        keys_a == keys_b
    ), f"The following keys are not present in both dictionaries: {keys_a ^ keys_b}"
    for key in keys_a:
        assert_equal(a[key], b[key], key=key, rtol=rtol, atol=atol)


def assert_dicts_equal(a, b, key=None, rtol=1e-07, atol=0):
    for x, y in zip(a, b):
        assert_equal(x, y, key=key, rtol=rtol, atol=atol)


###############################################################################
# Helpers for doing tests
###############################################################################


@dataclass(frozen=True)
class FakeTopographyModel:
    """This model is used to create a Topography for being passed to analysis functions."""

    t: Topography
    name: str = "mytopo"
    is_periodic: bool = False

    def topography(self):
        """Return low level topography."""
        return self.t

    def get_absolute_url(self):
        return "some/url/"


class AnalysisResultMock:
    subject: Union[Tag, Surface, Topography] = None
    folder: Folder = None

    def __init__(self, subject: Union[Tag, Surface, Topography], folder: Folder = None):
        self.subject = subject
        self.folder = folder
        if self.folder is None and hasattr(self.subject, "permissions"):
            self.folder = Folder.objects.create(permissions=self.subject.permissions)


class DummyProgressRecorder:
    def set_progress(self, a, nsteps):
        """Do nothing."""
        pass  # dummy

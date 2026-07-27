import io
import time
import zipfile

import requests
from django.contrib.auth import get_user_model
from notifications.signals import notify

from ..taskapp.celeryapp import app
from .import_zip import import_container_zip

User = get_user_model()

# Terminal task states of a `TaskStateModel`, as reported by the REST API
TASK_SUCCESS = "su"
TASK_FAILURE = "fa"

# How long, and how often, to wait for a remote instance to build a container
CONTAINER_POLL_INTERVAL = 2  # seconds
CONTAINER_TIMEOUT = 600  # seconds


def _fetch_remote_container(session, async_download_url, timeout=CONTAINER_TIMEOUT,
                            poll_interval=CONTAINER_POLL_INTERVAL, sleep=time.sleep):
    """
    Ask a remote instance to build a ZIP container and return its bytes.

    The remote builds containers in a Celery task: a POST creates the container
    and the container is then polled until its task has finished.

    Parameters
    ----------
    session : requests.Session
        Session used for the requests.
    async_download_url : str
        URL that creates the container, as advertised by the remote in the
        `async_download_url` field of a publication.
    timeout : float, optional
        Give up after this many seconds.
    poll_interval : float, optional
        Seconds between polls.
    sleep : callable, optional
        Delay function, injectable for tests.

    Returns
    -------
    bytes
        The container.

    Raises
    ------
    RuntimeError
        If the remote task failed, produced no file, or did not finish in time.
    requests.exceptions.RequestException
        If any of the requests fails.
    """
    response = session.post(async_download_url)
    response.raise_for_status()
    container_url = response.json()["url"]

    deadline = time.monotonic() + timeout
    while True:
        response = session.get(container_url)
        response.raise_for_status()
        container = response.json()

        task_state = container["task_state"]
        if task_state == TASK_FAILURE:
            raise RuntimeError(
                "Remote instance failed to prepare the container: "
                f"{container.get('task_error') or 'unknown error'}"
            )
        if task_state == TASK_SUCCESS:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Remote instance did not prepare the container within {timeout} s."
            )
        sleep(poll_interval)

    file_url = (container.get("manifest") or {}).get("file")
    if file_url is None:
        raise RuntimeError(
            "Remote instance reported the container as ready but returned no file."
        )

    response = session.get(file_url)
    response.raise_for_status()
    return response.content


@app.task
def import_container_from_url(user, url, tag=None):
    """
    Import a container from a URL and store it in the database.

    This function sends a request to a specified URL expecting a JSON response
    that describes how to obtain the container, downloads it, imports it into
    the database, and notifies the requesting user of the successful import.

    A publication that has an archived container advertises it as
    'download_url'; that file is the one its DOI refers to, and fetching it is a
    plain GET. Otherwise the remote has to assemble the archive first, which is
    what 'async_download_url' is for.

    Parameters
    ----------
    user : `topobank.users.models.User` or int
        The ID of the user who requested the import or the user object itself.
    url : str
        The URL of the container to import.
    tag : Tag, optional
        The tag to associate with the imported container. Default is None.

    Returns
    -------
    int
        The ID of the imported container.

    Notes
    -----
    If the 'Accept' header is set to 'application/json', the expected response
    should be a JSON dictionary containing a 'download_url' or an
    'async_download_url' key.

    Raises
    ------
    requests.exceptions.RequestException
        If the request to the URL fails.
    KeyError
        If the response from the URL describes no way to download the container.
    RuntimeError
        If the remote instance cannot prepare the container.
    """
    # If we send json as a request header, then contact.engineering will respond with a JSON dictionary
    with requests.Session() as session:
        response = session.get(url, headers={'Accept': 'application/json'})
        response.raise_for_status()
        data = response.json()

        download_url = data.get('download_url')
        if download_url is None:
            # No archived container; ask the remote to build one
            container = _fetch_remote_container(
                session, data['async_download_url']
            )
        else:
            # Serve the archived container directly
            response = session.get(download_url)
            response.raise_for_status()
            container = response.content

        container_file = io.BytesIO(container)

    # Get user
    if not isinstance(user, User):
        user = User.objects.get(id=user)

    # Process archive
    with zipfile.ZipFile(container_file, mode='r') as z:
        surface, = import_container_zip(z, user, tag=tag.name if tag else None)

    # Notify user
    notify.send(sender=user, recipient=user, verb='imported', target=surface,
                description=f"Successfully import digital surface twin '{surface.name}' from URL {url}.")

    return surface

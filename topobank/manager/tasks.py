import io
import zipfile

import requests
from notifications.signals import notify

from ..taskapp.celeryapp import app
from ..users.models import User
from .containers import import_container_zip


@app.task
def import_container_from_url(user, url, tag=None):
    """
    Import a container from a URL and store it in the database.

    This function sends a request to a specified URL expecting a JSON response that contains
    a 'download_url' for the container. It then downloads the container, imports it into the
    database, and notifies the requesting user of the successful import.

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
    If the 'Accept' header is set to 'application/json', the expected response should be a JSON
    dictionary containing at least a 'download_url' key.

    Raises
    ------
    requests.exceptions.RequestException
        If the request to the URL fails.
    ValueError
        If the response from the URL does not contain a 'download_url'.
    """
    # If we send json as a request header, then contact.engineering will respond with a JSON dictionary
    response = requests.get(url, headers={'Accept': 'application/json'})
    data = response.json()
    download_url = data['download_url']

    # Then download and read container
    container_response = requests.get(download_url)
    container_file = io.BytesIO(container_response.content)

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

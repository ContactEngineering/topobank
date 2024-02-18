import io
import zipfile

import requests

from ..taskapp.celeryapp import app
from ..users.models import User
from .containers import import_container


@app.task
def import_container_from_url(user_id, url):
    """
    Import a container from a URL and store it in the database.

    Parameters
    ----------
    user_id : int
        id of user who requested the import.
    url : str
        URL of the container to import.

    Returns
    -------
    container_id : int
        ID of the imported container.
    """
    # If we send json as a request header, then contact.engineering will response with a JSON dictionary
    response = requests.get(url, headers={'Accept': 'application/json'})
    data = response.json()
    download_url = data['download_url']

    # Then download and read container
    container_response = requests.get(download_url)
    container_file = io.BytesIO(container_response.content)

    # Get user
    user = User.objects.get(id=user_id)

    # Process archive
    with zipfile.Zipfile(container_file, mode='r') as z:
        surface, = import_container(z, user)

    return surface.id

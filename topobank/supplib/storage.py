import logging

from django.core.files.storage import default_storage

_log = logging.getLogger(__name__)


def default_storage_replace(name, content):
    """
    Write a file to the default storage, but replacing a potentially existing
    file. This is necessary because Django will rename the newly uploaded file
    if an object of the same name already exists. The function raises an error
    if Django deviates from the given name.

    Parameters
    ----------
    name : str
        Name of the file.
    content : stream
        Contents of the file.
    """
    if default_storage.exists(name):
        default_storage.delete(name)
    actual_name = default_storage.save(name, content)
    if actual_name != name:
        raise IOError(
            f"Trying to store file with name '{name}', but Django "
            f"storage renamed this file to '{actual_name}'."
        )
    return actual_name


def recursive_delete(prefix):
    """
    Delete everything underneath a prefix.

    Parameters
    ----------
    prefix : str
        Prefix to delete.
    """
    _log.info(f"Recursive delete of {prefix}")
    directories, filenames = default_storage.listdir(prefix)
    for filename in filenames:
        _log.info(f"Deleting file {prefix}/{filename}...")
        default_storage.delete(f"{prefix}/{filename}")
    for directory in directories:
        _log.info(f"Deleting directory {prefix}/{directory}...")
        recursive_delete(f"{prefix}/{directory}")
        default_storage.delete(f"{prefix}/{directory}")

"""
Converter functions for Django models to muFlow schemas.

This module converts topobank Django models (Tag, Surface, Topography)
to muFlow's Django-independent DatasetInfo schema.
"""

import logging
from typing import Optional, Union

from django.conf import settings

from ...manager.models import Surface, Tag, Topography
from ...properties.models import Property

_log = logging.getLogger(__name__)


def get_topography_file_url(topography: Topography) -> str:
    """
    Get the file URL for a topography's datafile.

    For S3 storage, this returns a presigned URL.
    For local storage, this returns the file path.

    Parameters
    ----------
    topography : Topography
        The topography model instance.

    Returns
    -------
    str
        URL or path to the topography's datafile.
    """
    if not topography.datafile:
        raise ValueError(f"Topography {topography.id} has no datafile")

    if settings.USE_S3_STORAGE:
        # Generate presigned URL for S3
        return topography.datafile.url
    else:
        # Return local file path
        return topography.datafile.file.path


def get_surface_file_url(surface: Surface) -> str:
    """
    Get the file URL for the first topography of a surface.

    Parameters
    ----------
    surface : Surface
        The surface model instance.

    Returns
    -------
    str
        URL or path to the topography's datafile.
    """
    first_topography = surface.topography_set.first()
    if first_topography is None:
        raise ValueError(f"Surface {surface.id} has no topographies")
    return get_topography_file_url(first_topography)


def get_property_value(
    surface: Surface, property_name: str
) -> Optional[Union[float, str]]:
    """
    Get the property value for a surface.

    Parameters
    ----------
    surface : Surface
        The surface model instance.
    property_name : str
        Name of the property to retrieve.

    Returns
    -------
    float | str | None
        The property value, or None if not found.
    """
    try:
        prop = Property.objects.get(
            surfaces=surface,
            name=property_name,
        )
        return prop.value
    except Property.DoesNotExist:
        return None
    except Property.MultipleObjectsReturned:
        # If multiple properties exist, use the first one
        prop = Property.objects.filter(
            surfaces=surface,
            name=property_name,
        ).first()
        return prop.value if prop else None


def convert_surface_to_info(
    surface: Surface, property_name: str
) -> dict:
    """
    Convert a Surface model to a SurfaceInfo dict.

    Parameters
    ----------
    surface : Surface
        The surface model instance.
    property_name : str
        Name of the property for training.

    Returns
    -------
    dict
        SurfaceInfo-compatible dictionary.
    """
    return {
        "id": str(surface.id),
        "name": surface.name,
        "file_path": get_surface_file_url(surface),
        "property_value": get_property_value(surface, property_name),
    }


def convert_tag_to_dataset(tag: Tag, property_name: str) -> dict:
    """
    Convert a Tag and its descendant surfaces to a DatasetInfo dict.

    Parameters
    ----------
    tag : Tag
        The tag model instance. Must have been authorized with a user
        via tag.authorize_user().
    property_name : str
        Name of the property for training.

    Returns
    -------
    dict
        DatasetInfo-compatible dictionary that can be used with muFlow workflows.
    """
    surfaces = tag.get_descendant_surfaces()

    surface_infos = []
    for surface in surfaces:
        try:
            info = convert_surface_to_info(surface, property_name)
            surface_infos.append(info)
        except ValueError as e:
            _log.warning(f"Skipping surface {surface.id}: {e}")
            continue

    return {
        "surfaces": surface_infos,
        "property_name": property_name,
    }


def convert_surface_to_dataset(surface: Surface, property_name: str) -> dict:
    """
    Convert a single Surface to a DatasetInfo dict.

    Parameters
    ----------
    surface : Surface
        The surface model instance.
    property_name : str
        Name of the property for training.

    Returns
    -------
    dict
        DatasetInfo-compatible dictionary.
    """
    return {
        "surfaces": [convert_surface_to_info(surface, property_name)],
        "property_name": property_name,
    }

import base64
import functools
import json
import logging
import tempfile
import traceback

import markdown2
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.files import File
from django.core.files.storage import default_storage
from django.db.models import Q
from guardian.core import ObjectPermissionChecker
from rest_framework.reverse import reverse
from storages.utils import clean_name

from SurfaceTopography import open_topography
from SurfaceTopography.IO import readers as surface_topography_readers
from SurfaceTopography.IO.DZI import write_dzi

from ..supplib.storage import default_storage_replace



def api_to_guardian(api_permission):
    """
    Translate a REST API permissions to a list of Django guardian permissions.
    The API exposes the following permissions:
        'no-access': No access to the dataset
        'view': Basic view access, corresponding to 'view_surface'
        'edit': Edit access, corresponding to 'view_surface' and
            'change_surface'
        'full': Full access (essentially transfer), corresponding to
            'view_surface', 'change_surface', 'delete_surface',
            'share_surface' and 'publish_surface'
    """
    _permissions = {
        "no-access": [],
        "view": ["view_surface"],
        "edit": ["view_surface", "change_surface"],
        "full": [
            "view_surface",
            "change_surface",
            "delete_surface",
            "share_surface",
            "publish_surface",
        ],
    }

    return _permissions[api_permission]


def guardian_to_api(guardian_permissions):
    """
    Translate a list of Django guardian permissions to an API permission
    keyword. The API exposes the following permissions:
        'no-access': No access to the dataset
        'view': Basic view access, corresponding to 'view_surface'
        'edit': Edit access, corresponding to 'view_surface' and
            'change_surface'
        'full': Full access (essentially transfer), corresponding to
            'view_surface', 'change_surface', 'delete_surface',
            'share_surface' and 'publish_surface'
    """

    api_permission = "no-access"
    if "view_surface" in guardian_permissions:
        api_permission = "view"
        if "change_surface" in guardian_permissions:
            api_permission = "edit"
            if (
                "delete_surface" in guardian_permissions
                and "share_surface" in guardian_permissions
                and "publish_surface" in guardian_permissions
            ):
                api_permission = "full"
    return api_permission


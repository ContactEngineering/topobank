def api_to_guardian(api_permission):
    """
    Translate a REST API permissions to a list of Django guardian permissions.
    The API exposes the following permissions:
        None: No access to the dataset
        'view': Basic view access, corresponding to 'view_surface'
        'edit': Edit access, corresponding to 'view_surface' and
            'change_surface'
        'full': Full access (essentially transfer), corresponding to
            'view_surface', 'change_surface', 'delete_surface',
            'share_surface' and 'publish_surface'
    """
    _permissions = {
        None: [],
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
        None: No access to the dataset
        'view': Basic view access, corresponding to 'view_surface'
        'edit': Edit access, corresponding to 'view_surface' and
            'change_surface'
        'full': Full access (essentially transfer), corresponding to
            'view_surface', 'change_surface', 'delete_surface',
            'share_surface' and 'publish_surface'
    """

    api_permission = None
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

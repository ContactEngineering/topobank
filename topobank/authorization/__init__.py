def get_permission_model():
    from django.apps import apps
    from django.conf import settings
    return apps.get_model(
        getattr(settings, 'TOPOBANK_PERMISSION_MODEL', 'authorization.PermissionSet'),
        require_ready=False
    )


def get_organization_model():
    from django.apps import apps
    from django.conf import settings
    model = getattr(settings, 'TOPOBANK_ORGANIZATION_MODEL', 'organizations.Organization')
    if not model:
        return None
    return apps.get_model(model, require_ready=False)


def get_user_permission_model():
    from django.apps import apps
    from django.conf import settings
    return apps.get_model(
        getattr(settings, 'TOPOBANK_USER_PERMISSION_MODEL', 'authorization.UserPermission'),
        require_ready=False
    )


def get_anonymous_user():
    """Return the configured anonymous user, or ``None`` if not configured.

    Deployments without an anonymous-user concept can leave
    ``TOPOBANK_ANONYMOUS_USER_GETTER`` unset; callers must then handle
    ``None`` (typically by skipping anonymous-related logic).
    """
    from django.conf import settings
    from django.utils.module_loading import import_string
    getter = getattr(settings, 'TOPOBANK_ANONYMOUS_USER_GETTER', None)
    if getter is None:
        return None
    return import_string(getter)()

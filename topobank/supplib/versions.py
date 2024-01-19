import importlib

from django.conf import settings


def get_versions():
    return {
        pkg_name: {
            'version': eval(version_expr, {pkg_name: importlib.import_module(pkg_name)}),
            'license': license,
            'homepage': homepage
        } for pkg_name, version_expr, license, homepage in settings.TRACKED_DEPENDENCIES
    }

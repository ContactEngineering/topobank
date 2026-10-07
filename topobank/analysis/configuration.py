"""
Provenance: which package versions a workflow result was computed with.
"""

import logging

from django.conf import settings
from django.db import transaction

from ..supplib.db import advisory_lock
from ..taskapp.models import Configuration
from ..taskapp.utils import get_package_version

_log = logging.getLogger(__name__)


def get_current_configuration():
    """
    Determine current configuration (package versions) and create appropriate
    database entries.

    The configuration is needed in order to track down analysis results to specific
    module and package versions. Like this it is possible to find all analyses which
    have been calculated with buggy packages.

    :return: Configuration instance which can be used for analyses
    """
    versions = [
        get_package_version(pkg_name, version_expr)
        for pkg_name, version_expr, license, homepage in settings.TRACKED_DEPENDENCIES
    ]

    def make_config_from_versions():
        c = Configuration.objects.create()
        c.versions.set(versions)
        return c

    # Serialize the check-then-create so concurrent workers (e.g. right after a
    # dependency version bump) do not each create a redundant Configuration for
    # the same version set. Doing the create and versions.set() inside one
    # transaction also means a Configuration is never observed with an empty
    # versions set. The advisory lock is released when the transaction commits.
    current_version_ids = set(v.id for v in versions)
    with transaction.atomic(), advisory_lock("current-configuration"):
        if Configuration.objects.count() == 0:
            return make_config_from_versions()

        # Find out whether the latest configuration has exactly these versions
        latest_config = Configuration.objects.latest("valid_since")
        latest_version_ids = set(v.id for v in latest_config.versions.all())

        if current_version_ids == latest_version_ids:
            return latest_config
        else:
            return make_config_from_versions()

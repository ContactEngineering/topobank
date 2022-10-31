import importlib

from django.db import transaction

from topobank.analysis.models import Dependency, Version


class ConfigurationException(Exception):
    pass


def get_package_version_tuple(pkg_name, version_expr):
    """

    :param pkg_name: name of the package which is used in import statement
    :param version_expr: expression used to get the version from already imported module
    :return: version tuple
    """
    mod = importlib.import_module(pkg_name)

    version = eval(version_expr, {pkg_name: mod})

    version_tuple = version.split('.')

    try:
        major: int = int(version_tuple[0])
    except:
        raise ConfigurationException("Cannot determine major version of package '{}'. Full version string: {}",
                                     format(pkg_name, version))

    try:
        minor: int = int(version_tuple[1])
    except:
        raise ConfigurationException("Cannot determine minor version of package '{}'. Full version string: {}",
                                     format(pkg_name, version))

    try:
        micro: int = int(version_tuple[2].split('+')[0])  # because of version strings like '0.51.0+0.g2c488bd.dirty'
    except:
        micro = None

    return major, minor, micro


@transaction.atomic
def get_package_version_instance(pkg_name, version_expr):
    """Return version instance for currently installed version of a package.

    :param pkg_name: name of the package which is used in import statement
    :param version_expr: expression used to get the version from already imported module
    :return: Version instance
    """
    major, minor, micro = get_package_version_tuple(pkg_name, version_expr)

    dep, created = Dependency.objects.get_or_create(import_name=pkg_name)

    # make sure, this version is available in database
    version, created = Version.objects.get_or_create(dependency=dep, major=major, minor=minor, micro=micro)

    return version

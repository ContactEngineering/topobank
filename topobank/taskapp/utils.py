import importlib

from topobank.analysis.models import Configuration, Dependency, Version

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
        micro: int = int(version_tuple[2])
    except:
        micro = None

    return major, minor, micro


def get_package_version_instance(pkg_name, version_attr):
    """Return version instance for currently installed version of a package.

    :param pkg_name:
    :param version_attr:
    :return: Version instance
    """
    major, minor, micro = get_package_version_tuple(pkg_name, version_attr)

    dep, created = Dependency.objects.get_or_create(import_name=pkg_name)

    # make sure, this version is available in database
    version, created = Version.objects.get_or_create(dependency=dep, major=major, minor=minor, micro=micro)

    return version

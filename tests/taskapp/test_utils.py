"""Tests for version-string parsing in topobank.taskapp.utils."""

from topobank.taskapp.utils import _get_package_version_tuple


def _parse(version_string):
    # The version expression is evaluated against the imported package namespace;
    # passing a string literal lets us control the parsed version deterministically.
    return _get_package_version_tuple("numpy", repr(version_string))


def test_parse_standard_version():
    assert _parse("1.66.3") == (1, 66, 3, None)


def test_parse_version_with_extra_suffix():
    major, minor, micro, extra = _parse("1.66.3.dev96+g53c1c0d2.dirty")
    assert (major, minor, micro) == (1, 66, 3)
    assert extra and "dev96" in extra


def test_parse_version_with_local_micro_suffix():
    # e.g. '0.51.0+0.g2c488bd.dirty' -> micro parsed from before the '+'
    major, minor, micro, extra = _parse("0.51.0+0.g2c488bd.dirty")
    assert (major, minor, micro) == (0, 51, 0)


def test_parse_non_integer_first_part_is_all_extra():
    assert _parse("f0feec2+dirty") == (0, 0, None, "f0feec2+dirty")


def test_parse_two_component_version():
    major, minor, micro, extra = _parse("2.1")
    assert (major, minor, micro) == (2, 1, None)


def test_parse_single_component_version():
    major, minor, micro, extra = _parse("7")
    assert major == 7
    assert minor == 0
    assert micro is None

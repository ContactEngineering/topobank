"""Tests for topobank.supplib.versions."""

from topobank.supplib.versions import get_versions


def test_get_versions_structure():
    versions = get_versions()
    assert isinstance(versions, dict)

    # These are declared in TRACKED_DEPENDENCIES in the test settings.
    assert "topobank" in versions
    assert "numpy" in versions

    for pkg_name, info in versions.items():
        assert set(info.keys()) == {"version", "license", "homepage"}
        assert isinstance(info["version"], str) and info["version"]
        assert isinstance(info["license"], str) and info["license"]
        assert info["homepage"].startswith("http")

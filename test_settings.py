"""
Settings module named by ``DJANGO_SETTINGS_MODULE`` (see ``pyproject.toml``).

Deliberately a re-export and nothing else. These settings used to be a second,
near-identical copy of :mod:`topobank.test_settings`, and the two drifted: the
storage configuration was added to that one while the test run loaded this one,
so CI ran its S3 matrix entry against the local filesystem. Keeping one
definition is what makes that impossible rather than merely unlikely.

Do not add settings here. Anything the test suite needs belongs in
:mod:`topobank.test_settings`, which downstream plugins import as well.
"""

from topobank.test_settings import *  # noqa: F401,F403

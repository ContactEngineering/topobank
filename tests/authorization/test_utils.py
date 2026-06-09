import pytest

from topobank.authorization import (
    get_anonymous_user,
    get_organization_model,
    get_permission_model,
    get_user_permission_model,
)
from topobank.authorization.models import levels_with_access


def test_levels_with_access():
    assert levels_with_access("full") == {"full"}
    assert levels_with_access("edit") == {"edit", "full"}
    assert levels_with_access("view") == {"view", "edit", "full"}


def test_get_permission_models_resolve():
    assert get_permission_model() is not None
    assert get_user_permission_model() is not None
    # In the test configuration an organization model is configured.
    assert get_organization_model() is not None


def test_get_organization_model_returns_none_when_unset(settings):
    # Use the pytest-django `settings` fixture rather than Django's
    # @override_settings decorator: the decorator is only reliably applied to
    # unittest TestCase methods, not plain pytest functions.
    settings.TOPOBANK_ORGANIZATION_MODEL = ""
    assert get_organization_model() is None


@pytest.mark.django_db
def test_get_anonymous_user_returns_user():
    assert get_anonymous_user() is not None


def test_get_anonymous_user_returns_none_when_unconfigured(settings):
    # When no getter is configured, callers receive None (and must handle it).
    settings.TOPOBANK_ANONYMOUS_USER_GETTER = None
    assert get_anonymous_user() is None

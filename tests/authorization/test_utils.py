import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

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


@override_settings(TOPOBANK_ORGANIZATION_MODEL="")
def test_get_organization_model_returns_none_when_unset():
    assert get_organization_model() is None


@pytest.mark.django_db
def test_get_anonymous_user_returns_user():
    assert get_anonymous_user() is not None


@override_settings(TOPOBANK_ANONYMOUS_USER_GETTER=None)
def test_get_anonymous_user_requires_configuration():
    with pytest.raises(ImproperlyConfigured):
        get_anonymous_user()

import pytest

from ..utils import get_default_group
from topobank.users.models import DEFAULT_GROUP_NAME


@pytest.mark.django_db
def test_default_group_helper():
    assert get_default_group().name == DEFAULT_GROUP_NAME


@pytest.mark.django_db
def test_new_user_has_default_group(user_alice):
    assert get_default_group() in user_alice.groups.all()

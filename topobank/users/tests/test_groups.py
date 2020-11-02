import pytest

from django.core.management import call_command

from .test_utils import UserFactory
from ..utils import get_default_group
from topobank.users.models import DEFAULT_GROUP_NAME


@pytest.mark.django_db
def test_management_command_for_default_group():

    user = UserFactory()
    from django.contrib.auth.models import Group

    # remove group if existing
    try:
        group = Group.objects.get(name=DEFAULT_GROUP_NAME)
        user.groups.remove(group)
        group.delete()
    except Group.DoesNotExist:
        pass

    assert user.groups.count() == 0

    call_command('ensure_default_group')
    from django.contrib.auth.models import Group
    default_group = Group.objects.get(name=DEFAULT_GROUP_NAME)

    assert user.groups.count() == 1
    assert user.groups.first() == default_group


@pytest.mark.django_db
def test_default_group_helper():
    assert get_default_group().name == DEFAULT_GROUP_NAME


@pytest.mark.django_db
def test_new_user_has_default_group(user_alice):
    assert get_default_group() in user_alice.groups.all()

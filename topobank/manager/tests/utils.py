import pytest
from django.core.management import call_command

from topobank.users.models import User

@pytest.fixture(scope='session')
def two_topos(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        call_command('loaddata', 'two_topographies.yaml')

        # Fix the passwords of fixtures
        for user in User.objects.all():
            user.set_password(user.password)
            user.save()

        # like this we can have clear-text passwords in test fixtures

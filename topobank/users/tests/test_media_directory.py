import pytest
import os.path
from django.conf import settings

from topobank.users.tests.factories import UserFactory

@pytest.mark.django_db
def test_media_dir():

    user = UserFactory(username='testuser')
    expected_dir = settings.MEDIA_ROOT + '/topographies/user_{}'.format(user.id)

    assert expected_dir == user.get_media_path()

    assert os.path.exists(expected_dir)


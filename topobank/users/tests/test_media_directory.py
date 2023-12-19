import pytest

from topobank.users.tests.factories import UserFactory


@pytest.mark.django_db
def test_media_dir():
    user = UserFactory(username='testuser')

    assert user.get_media_path().endswith('topographies/user_{}'.format(user.id))

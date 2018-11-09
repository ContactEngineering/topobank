import pytest

from django.conf import settings

import os.path

@pytest.mark.django_db
def test_media_dir(django_user_model):

    user = django_user_model.objects.create_user(name='Test User',
                                                 username='testuser',
                                                 email='test@example.org',
                                                 password='bla$12345')
    user.save()
    expected_dir = settings.MEDIA_ROOT + '/topographies/user_{}'.format(user.id)

    assert expected_dir == user.get_media_path()

    assert os.path.exists(expected_dir)


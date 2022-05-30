import pytest

from django.test import SimpleTestCase
from django.conf import settings

from topobank.manager.tests.utils import UserFactory


@pytest.mark.skipif(settings.CHALLENGE_REDIRECT_URL == '', reason="No URL for challenge given in settings.")
@pytest.mark.django_db
def test_redirect_for_challenge(client):
    user = UserFactory()
    client.force_login(user)
    response = client.get('/challenge/')
    SimpleTestCase().assertRedirects(response, settings.CHALLENGE_REDIRECT_URL,
                                     status_code=302, fetch_redirect_response=False)

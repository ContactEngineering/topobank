import pytest

from .factories import UserFactory, OrcidSocialAccountFactory

@pytest.mark.django_db
def test_absolute_url():
    user = UserFactory(username="testuser")
    assert user.get_absolute_url() == "/users/testuser/"

@pytest.mark.django_db
def test__str__():
    user = UserFactory(username="testuser")
    assert str(user) == "testuser"

@pytest.mark.django_db
def test_orcid_info():
    OrcidSocialAccountFactory.reset_sequence(13)
    user_id = "0013-0013-0013-0013"
    user = UserFactory()
    assert user.orcid_id == user_id
    assert user.orcid_uri() == 'https://orcid.org/'+user_id

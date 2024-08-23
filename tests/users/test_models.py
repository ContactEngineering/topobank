import pytest

from topobank.testing.factories import OrcidSocialAccountFactory, UserFactory


@pytest.mark.django_db
def test_absolute_url():
    user = UserFactory(username="testuser")
    assert user.get_absolute_url() == f"/users/api/user/{user.id}/"


@pytest.mark.django_db
def test__str__():
    OrcidSocialAccountFactory.reset_sequence(13)
    user = UserFactory(username="testuser", name="Test User")
    assert str(user) == "Test User (0013-0013-0013-0013)"


@pytest.mark.django_db
def test_orcid_info():
    OrcidSocialAccountFactory.reset_sequence(13)
    user_id = "0013-0013-0013-0013"
    user = UserFactory()
    assert user.orcid_id == user_id
    assert user.orcid_uri() == "https://orcid.org/" + user_id

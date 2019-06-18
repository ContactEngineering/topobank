import pytest

from .factories import UserFactory, OrcidSocialAccountFactory
from topobank.manager.tests.utils import SurfaceFactory

@pytest.mark.django_db
def test_absolute_url():
    user = UserFactory(username="testuser")
    assert user.get_absolute_url() == "/users/testuser/"

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
    assert user.orcid_uri() == 'https://orcid.org/'+user_id

@pytest.mark.django_db
def test_is_sharing_with():

    user1 = UserFactory()
    user2 = UserFactory()

    assert not user1.is_sharing_with(user2)

    surface = SurfaceFactory(creator=user1)
    surface.share(user2)

    assert user1.is_sharing_with(user2)



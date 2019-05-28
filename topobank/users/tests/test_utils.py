
from ..utils import are_collaborating
from topobank.manager.tests.utils import UserFactory, SurfaceFactory

def test_collaborators(django_user_model):

    user1 = django_user_model.objects.create_user(username='testuser1', password="abcd$1234")
    user2 = django_user_model.objects.create_user(username='testuser2', password="abcd$5678")

    # these users don't share anything yet
    assert not are_collaborating(user1, user2)

    # a user is always collaborating with herself
    assert are_collaborating(user1, user1)
    assert are_collaborating(user2, user2)

    # create surface and share
    surface1 = SurfaceFactory(creator=user1)
    surface1.share(user2)

    assert surface1.is_shared(user2)
    assert not surface1.is_shared(user2, allow_change=True)

    # now they are collaborating
    assert are_collaborating(user1, user2)

    # share the other way round
    surface2 = SurfaceFactory(creator=user2)
    surface2.share(user2)

    # still collaborating
    assert are_collaborating(user1, user2)
    assert are_collaborating(user2, user1)

    # now remove all share
    surface1.unshare(user2)
    surface2.unshare(user1)

    # these users don't collaborate any more
    assert not are_collaborating(user1, user2)
    assert not are_collaborating(user2, user1)

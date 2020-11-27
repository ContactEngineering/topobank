import pytest
from django.urls import reverse
from django.contrib.auth.models import Permission

from .test_utils import are_collaborating, SurfaceFactory


@pytest.mark.django_db
def test_sharing_profile(client, django_user_model, handle_usage_statistics):

    user1 = django_user_model.objects.create_user(username='testuser1', password="abcd$1234")
    user2 = django_user_model.objects.create_user(username='testuser2', password="abcd$5678")

    # give both user permissions to skip all terms, we want to test independently from this
    skip_perm = Permission.objects.get(codename='can_skip_terms')
    user1.user_permissions.add(skip_perm)
    user2.user_permissions.add(skip_perm)

    assert client.login(username='testuser1', password='abcd$1234')

    response = client.get(reverse('users:detail', kwargs={'username': 'testuser1'}))  # same user
    assert response.status_code == 200

    #
    # both users don't share anything, so they can't see each others profiles
    #
    assert not are_collaborating(user1, user2)

    response = client.get(reverse('users:detail', kwargs={'username': 'testuser2'}))  # other user!!
    assert response.status_code == 403  # Forbidden

    # share sth. and the view of profile is possible
    surface = SurfaceFactory(creator=user1)
    surface.share(user2)

    assert are_collaborating(user1, user2)
    response = client.get(reverse('users:detail', kwargs={'username': 'testuser2'}))
    assert response.status_code == 200  # Allowed






import pytest
from django.urls import reverse
from django.core.exceptions import PermissionDenied

from ..models import Surface

@pytest.mark.django_db
def test_prevent_surface_access_by_other_user(client, django_user_model):

    surface_id = 1
    username1 = 'testuser1'
    password1 = 'abcd$1234'
    username2 = 'testuser2'
    password2 = 'abcd$5678'

    #
    # Create surface of user 1
    #
    user1 = django_user_model.objects.create_user(username=username1, password=password1)

    surface = Surface.objects.create(id=surface_id, name="Surface 1", user=user1)
    assert surface.id == surface_id
    surface.save()

    #
    # Login as user 2
    #
    django_user_model.objects.create_user(username=username2, password=password2)
    assert client.login(username=username2, password=password2)

    #
    # As user 2, try to access surface from user 1 with various views
    #
    # Each time, this should redirect to an access denied page
    #
    response = client.get(reverse('manager:surface-detail', kwargs=dict(pk=surface_id)))
    assert response.url == reverse('manager:access-denied')

    response = client.get(reverse('manager:surface-update', kwargs=dict(pk=surface_id)))
    assert response.url == reverse('manager:access-denied')

    response = client.get(reverse('manager:surface-delete', kwargs=dict(pk=surface_id)))
    assert response.url == reverse('manager:access-denied')


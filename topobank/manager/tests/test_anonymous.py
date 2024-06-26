import pytest
from django.shortcuts import reverse

from .utils import SurfaceFactory, Topography1DFactory, UserFactory

#
# The code in these tests rely on a middleware which replaces
# Django's AnonymousUser by the one of django guardian
#


@pytest.mark.django_db
def test_anonymous_user_cannot_change(client, handle_usage_statistics):
    bob = UserFactory(name="Bob")
    surface_name = "Diamond Structure"
    surface = SurfaceFactory(creator=bob, name=surface_name)
    topo = Topography1DFactory(surface=surface)

    response = client.get(reverse('manager:surface-api-list'))
    assert response.status_code == 405  # Method not allowed

    response = client.get(reverse('manager:surface-api-detail', kwargs=dict(pk=surface.pk)))
    assert response.status_code == 404  # Not found

    response = client.post(reverse('manager:surface-api-list'))
    assert response.status_code == 403  # Forbidden

    response = client.put(reverse('manager:surface-api-detail', kwargs=dict(pk=surface.pk)))
    assert response.status_code == 403  # Forbidden

    response = client.patch(reverse('manager:surface-api-detail', kwargs=dict(pk=surface.pk)))
    assert response.status_code == 403  # Forbidden

    response = client.delete(reverse('manager:surface-api-detail', kwargs=dict(pk=surface.pk)))
    assert response.status_code == 403  # Forbidden

    response = client.get(reverse('manager:topography-api-list'))
    assert response.status_code == 405  # Method not allowed

    response = client.get(reverse('manager:topography-api-detail', kwargs=dict(pk=topo.pk)))
    assert response.status_code == 404  # Not found

    response = client.post(reverse('manager:topography-api-list'))
    assert response.status_code == 403  # Forbidden

    response = client.put(reverse('manager:topography-api-detail', kwargs=dict(pk=topo.pk)))
    assert response.status_code == 403  # Forbidden

    response = client.patch(reverse('manager:topography-api-detail', kwargs=dict(pk=topo.pk)))
    assert response.status_code == 403  # Forbidden

    response = client.delete(reverse('manager:topography-api-detail', kwargs=dict(pk=topo.pk)))
    assert response.status_code == 403  # Forbidden

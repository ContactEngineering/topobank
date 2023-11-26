import pytest
from django.urls import reverse

from ...publication.models import Publication

from .utils import SurfaceFactory, UserFactory


@pytest.mark.django_db
def test_sharing_status_filter(api_client, example_authors, handle_usage_statistics):
    lancelot = UserFactory(name="lancelot")
    parceval = UserFactory(name="parceval")

    surface_own_hidden = SurfaceFactory(name="own-hidden", creator=lancelot)

    surface_shared_egress = SurfaceFactory(name="shared-egress", creator=lancelot)
    surface_shared_egress.share(parceval)

    surface_published_egress = SurfaceFactory(name="published-egress", creator=lancelot)
    Publication.publish(surface_published_egress, 'cc0-1.0', example_authors)
    # NOTE THAT THIS CREATES A COPY !!!!

    surface_shared_ingress = SurfaceFactory(name="shared-ingress", creator=parceval)
    surface_shared_ingress.share(lancelot)
    surface_published_ingress = SurfaceFactory(name="published-ingress", creator=parceval)
    Publication.publish(surface_published_ingress, 'cc0-1.0', example_authors)
    surface_published_invisible = SurfaceFactory(name="invisible", creator=parceval)

    api_client.force_login(lancelot)

    result = api_client.get(reverse('manager:search') + '?sharing_status=all').data["page_results"]
    assert len(result) == 6

    result = api_client.get(reverse('manager:search') + '?sharing_status=own').data["page_results"]
    assert len(result) == 4

    result = api_client.get(reverse('manager:search') + '?sharing_status=shared_ingress').data["page_results"]
    assert len(result) == 1
    assert result[0]['name'] == "shared-ingress"


    result = api_client.get(reverse('manager:search') + '?sharing_status=published_ingress').data["page_results"]
    assert len(result) == 1
    assert result[0]['name'] == "published-ingress"

    result = api_client.get(reverse('manager:search') + '?sharing_status=shared_egress').data["page_results"]
    assert len(result) == 1
    assert result[0]['name'] == "shared-egress"

    result = api_client.get(reverse('manager:search') + '?sharing_status=published_egress').data["page_results"]
    assert len(result) == 1
    assert result[0]['name'] == "published-egress"

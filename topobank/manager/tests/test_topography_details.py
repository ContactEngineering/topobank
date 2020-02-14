import pytest

from django.shortcuts import reverse

from .utils import topography_with_broken_pyco_topography  # needed as fixture
from topobank.utils import assert_in_content

@pytest.mark.django_db
def test_error_message_when_pyco_topography_cannot_be_loaded(client, topography_with_broken_pyco_topography):

    client.force_login(user=topography_with_broken_pyco_topography.surface.creator)

    response = client.get(reverse('manager:topography-detail',
                                  kwargs=dict(pk=topography_with_broken_pyco_topography.pk)))

    # there should be no internal server error
    assert response.status_code == 200

    # there should be an error message showing that the topography could not be loaded
    assert_in_content(response, f"{topography_with_broken_pyco_topography.name}")
    assert_in_content(response, f"(id: {topography_with_broken_pyco_topography.id}) cannot be loaded unexpectedly.")
    assert_in_content(response, "send us an e-mail about this issue")



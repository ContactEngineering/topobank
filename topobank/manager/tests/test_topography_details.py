import pytest

from django.shortcuts import reverse

from .utils import topography_loaded_from_broken_file  # needed as fixture
from topobank.utils import assert_in_content

@pytest.mark.django_db
def test_error_message_when_topography_file_cannot_be_loaded(client, topography_loaded_from_broken_file):

    client.force_login(user=topography_loaded_from_broken_file.surface.creator)

    response = client.get(reverse('manager:topography-detail',
                                  kwargs=dict(pk=topography_loaded_from_broken_file.pk)))

    # there should be no internal server error
    assert response.status_code == 200

    # there should be an error message showing that the topography could not be loaded
    assert_in_content(response, f"{topography_loaded_from_broken_file.name}")
    assert_in_content(response, f"(id: {topography_loaded_from_broken_file.id}) cannot be loaded unexpectedly.")
    assert_in_content(response, "send us an e-mail about this issue")



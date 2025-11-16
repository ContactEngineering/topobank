import pytest
from django.shortcuts import reverse

from topobank.testing.utils import assert_in_content


@pytest.mark.skip(
    "Does not work currently because plot is now loaded via AJAX - could this be tested differently?"
)
@pytest.mark.django_db
def test_error_message_when_topography_file_cannot_be_loaded(
    client, topography_loaded_from_broken_file, handle_usage_statistics
):
    client.force_login(user=topography_loaded_from_broken_file.surface.created_by)

    response = client.get(
        reverse(
            "manager:topography-detail",
            kwargs=dict(pk=topography_loaded_from_broken_file.pk),
        )
    )

    # there should be no internal server error
    assert response.status_code == 200

    # there should be an error message showing that the topography could not be loaded
    assert_in_content(response, f"{topography_loaded_from_broken_file.name}")
    assert_in_content(
        response,
        f"(id: {topography_loaded_from_broken_file.id}) cannot be loaded unexpectedly.",
    )
    assert_in_content(response, "send us an e-mail about this issue")

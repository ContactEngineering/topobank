import pytest

from topobank.manager.tests.utils import SurfaceFactory, TopographyFactory
from splinter_tests.utils import goto_select_page, goto_publications_page


@pytest.mark.django_db
def test_publishing(user_alice_logged_in, user_bob, handle_usage_statistics):

    browser, user_alice = user_alice_logged_in

    #
    # Generate surface with topography for Alice.
    #
    surface_name = "First published surface"

    surface = SurfaceFactory(creator=user_alice, name=surface_name)
    topography = TopographyFactory(surface=surface)

    #
    # When going to the "Published surfaces tab", nothing is listed
    #
    goto_publications_page(browser)
    assert browser.is_text_present("You haven't published any surfaces yet.")


    #
    # Alice opens properties for the surface
    #
    goto_select_page(browser)
    surface_link = browser.links.find_by_partial_text(surface_name)
    surface_link.click()

    browser.is_text_present("Analyze this surface")

    #
    # Alice presses "Publish" button. The extra "Publish surface ..." tab opens.
    #
    browser.is_text_present("Publish")
    publish_btn = browser.links.find_by_partial_text("Publish")
    publish_btn.click()

    #
    # There are three licenses for selection. Alice chooses the "CC BY-SA"
    # license
    #

    #
    # Alice presses Publish. A new tab opens which asks again whether she's really sure:
    #

    #
    # Alice presses "Yes, publish". The extra tab is closed and Alice is taken
    # to the "Publish" tab.
    #

    #
    # Here the published surface is listed.
    # Alice presses the link and enters the property page for the surface.

    #
    # Here a "published by you" badge is shown.
    #

    #
    # She opens the permissions and sees that Everyone has read permissions
    # and nothing else.
    #

    #
    # Alice logs out.
    # Bob logs in and enters the "Select" tab.
    #

    #
    # He filters for "Only published surfaces"
    #

    #
    # Alice surface is visible. He opens the properties and sees
    # the "published by Alice" badge.
    #
    pass






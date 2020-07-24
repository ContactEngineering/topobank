import pytest

from topobank.manager.tests.utils import SurfaceFactory, TopographyFactory
from splinter_tests.utils import goto_select_page, goto_publications_page, \
    select_sharing_status, press_properties_for_item_by_name, num_items_in_result_table,\
    data_of_item_by_name


def press_yes_publish(browser):
    publish_btn = browser.find_by_name('save').first
    publish_btn.click()


def press_permissions(browser):
    browser.links.find_by_partial_text("Permissions").first.click()


def assert_only_permissions_everyone(browser):
    press_permissions(browser)
    # We have only string "Everyone" in the table
    permission_table = browser.find_by_id("permissions")
    assert permission_table.find_by_css("table td").text == "Everyone"


@pytest.mark.django_db
def test_publishing_form(user_alice_logged_in, user_bob, handle_usage_statistics):

    browser, user_alice = user_alice_logged_in

    #
    # Generate surface with topography for Alice.
    #
    surface_name = "First published surface"

    surface = SurfaceFactory(creator=user_alice, name=surface_name)
    # a topography is added later

    #
    # When going to the "Published surfaces tab", nothing is listed
    #
    goto_publications_page(browser)
    assert browser.is_text_present("You haven't published any surfaces yet.")


    #
    # Alice opens properties for the surface
    #
    goto_select_page(browser)
    press_properties_for_item_by_name(browser, surface_name)

    #
    # Alice presses "Publish" button. The extra "Publish surface ..." tab opens.
    #
    assert browser.is_text_present("Publish")
    publish_btn = browser.links.find_by_partial_text("Publish")
    publish_btn.click()

    #
    # Since no topography is available for the surface, a hint is shown
    #
    assert browser.is_text_present("This surface has no topographies yet")

    #
    # We add a topography and reload
    #
    TopographyFactory(surface=surface)
    browser.reload()

    #
    # There are three licenses for selection. Alice chooses the "CC BY-SA"
    # license
    #
    browser.choose('license', 'ccbysa-4.0')

    #
    # Alice presses Publish. She didn't check the checkboxes, we are still on page
    #
    press_yes_publish(browser)

    assert len(browser.find_by_name("save")) > 0

    #
    # Alice checks one checkbox, the other is still needed
    #
    browser.find_by_id('id_ready').first.click()

    press_yes_publish(browser)
    assert len(browser.find_by_name("save")) > 0

    # Alice checks the second and tries again to publish.
    # The extra tab is closed and Alice is taken
    # to the list of published surfaces.
    browser.find_by_id('id_agreed').first.click()

    press_yes_publish(browser)
    assert len(browser.find_by_name("save")) == 0
    assert browser.is_text_present("Surfaces published by you", wait_time=1)

    # Here the published surface is listed.
    # Alice presses the link and enters the property page for the surface.
    assert browser.is_text_present(surface_name)
    browser.find_by_css('td').find_by_text(surface_name).click()

    #
    # Here a "published by you" badge is shown.
    #
    assert browser.is_text_present("published by you")

    # She opens the permissions and sees that Everyone has read permissions
    # and nothing else.
    # The individual names are NOT listed.
    assert_only_permissions_everyone(browser)


@pytest.mark.django_db
def test_see_published_by_others(user_alice_logged_in, user_bob, handle_usage_statistics):

    browser, user_alice = user_alice_logged_in

    #
    # Alice has a surface, which is not published
    #
    SurfaceFactory(creator=user_alice, name="Alice's Surface")

    #
    # User Bob publishes a surface (here in the background)
    #
    surface_name = "Bob has published this"
    surface_description = "Valuable results."
    surface = SurfaceFactory(creator=user_bob, name=surface_name, description=surface_description)
    TopographyFactory(surface=surface)
    surface.publish('cc0')

    # Alice filters for published surfaces - enters
    # "Select" tab and chooses "Only published surfaces"
    #
    goto_select_page(browser)

    assert num_items_in_result_table(browser) == 2  # both surfaces are visible by default

    select_sharing_status(browser, 'published')
    assert num_items_in_result_table(browser) == 1  # only published is visible

    # Bobs surface is visible as only surface.
    # The version number is "1".
    data = data_of_item_by_name(browser, surface_name)
    assert data['description'] == surface_description
    assert data['version'] == "1"

    # Alice opens the properties and sees
    # the "published by Bob" badge.
    press_properties_for_item_by_name(browser, surface_name)
    browser.is_text_present('published by Bob Marley')

    # She opens the permissions and sees that Everyone has read permissions
    # and nothing else.
    # The individual names are NOT listed.
    assert_only_permissions_everyone(browser)






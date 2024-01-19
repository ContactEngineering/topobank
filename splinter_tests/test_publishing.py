import freezegun
import pytest

from topobank.manager.tests.utils import SurfaceFactory, Topography2DFactory
from topobank_publication.models import Publication

from splinter_tests.utils import goto_select_page, goto_publications_page, \
    select_sharing_status, press_view_for_item_by_name, num_items_in_result_table, \
    data_of_item_by_name, double_click_on_item_by_name


def press_yes_publish(browser):
    publish_btn = browser.find_by_name('save').first
    publish_btn.click()


def press_permissions(browser):
    browser.links.find_by_partial_text("Permissions").first.click()
    assert browser.is_text_present("This table lists users that can view, change, delete or share this digital "
                                   "surface twin.", wait_time=1)


def assert_only_permissions_everyone(browser):
    press_permissions(browser)
    # We have only string "Everyone" in the table
    permission_table = browser.find_by_id("permissions")
    assert permission_table.find_by_tag("td").text == "Everyone"  # does not work in Chrome


def select_radio_btn(browser, radio_id):
    radio_btn = browser.find_by_id(radio_id).first
    browser.execute_script("arguments[0].click();", radio_btn._element)


def press_insert_me_btn(browser, index=0):
    insert_me_btn = browser.find_by_css('.insert-me-btn')[index]
    insert_me_btn.click()


@pytest.mark.django_db
def test_publishing_form(user_alice_logged_in, handle_usage_statistics):
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
    press_view_for_item_by_name(browser, surface_name)

    #
    # Alice presses "Publish" button. The extra "Publish surface ..." tab opens.
    #
    assert browser.is_text_present("Publish")
    publish_btn = browser.links.find_by_partial_text("Publish")
    publish_btn.click()

    #
    # Since no topography is available for the surface, a hint is shown
    #
    assert browser.is_text_present("This surface has no measurements yet")

    #
    # We add a topography and reload
    #
    Topography2DFactory(surface=surface)
    browser.reload()

    #
    # There are three licenses for selection. Alice chooses the "CC BY-SA"
    # license
    #
    # browser.choose('license', 'ccbysa-4.0')  # this only works with standard HTML radio btn
    # radio_btn = browser
    select_radio_btn(browser, 'id_id_license_0_2')  # 'ccbysa-4.0'
    #
    # Alice presses Publish. She didn't check the checkboxes, we are still on page
    #
    press_yes_publish(browser)

    assert len(browser.find_by_name("save")) > 0

    #
    # Alice checks one checkbox, the other is still needed and the authors
    #
    select_radio_btn(browser, 'id_copyright_hold')

    press_yes_publish(browser)
    assert len(browser.find_by_name("save")) > 0

    # Alice checks the second and tries again to publish.
    select_radio_btn(browser, 'id_agreed')
    assert len(browser.find_by_name("save")) > 0

    # Still now publishing: She hasn't entered an author yet.
    # She decides to enter herself as author by pressing the "user" button
    press_insert_me_btn(browser)

    # Now she tries again
    # The extra tab is closed and Alice is taken
    # to the list of published surfaces.
    press_yes_publish(browser)
    assert len(browser.find_by_name("save")) == 0
    assert browser.is_text_present("Surfaces published by you", wait_time=1)

    # Here the published surface is listed. Also the author names are listed, here just Alice' name.
    # Alice presses the link and enters the property page for the surface.
    assert browser.is_text_present(surface_name)
    assert browser.is_text_present(user_alice.name)
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
def test_publishing_form_multiple_authors(user_alice_logged_in, handle_usage_statistics):
    """Test that multiple authors can be entered.
    """
    browser, user_alice = user_alice_logged_in

    #
    # Generate surface with topography for Alice.
    #
    surface_name = "First published surface"

    surface = SurfaceFactory(creator=user_alice, name=surface_name)
    Topography2DFactory(surface=surface)

    #
    # Alice opens properties for the surface
    #
    goto_select_page(browser)
    press_view_for_item_by_name(browser, surface_name)

    #
    # Alice presses "Publish" button. The extra "Publish surface ..." tab opens.
    #
    assert browser.is_text_present("Publish")
    publish_btn = browser.links.find_by_partial_text("Publish")
    publish_btn.click()

    #
    # Alice adds herself as first author
    #
    press_insert_me_btn(browser)

    #
    # Alice presses "One more author" button, adds one author
    #
    assert browser.is_text_present('One more author', wait_time=1)
    one_more_author_btn = browser.find_by_id('one_more_author_btn')
    one_more_author_btn.click()

    assert browser.is_text_present("2. Author")
    browser.fill('author_1', "Queen of Hearts")

    #
    # Alice chooses the "CC BY-SA" license
    #
    select_radio_btn(browser, 'id_id_license_0_2')  # 'ccbysa-4.0'

    #
    # Alice checks the checkboxes
    #
    select_radio_btn(browser, 'id_copyright_hold')
    select_radio_btn(browser, 'id_agreed')

    press_yes_publish(browser)
    assert len(browser.find_by_name("save")) == 0
    assert browser.is_text_present("Surfaces published by you", wait_time=1)

    # Here the published surface is listed. And both author names.
    assert browser.is_text_present(surface_name)
    assert browser.is_text_present(user_alice.name)
    assert browser.is_text_present("Queen of Hearts")


@freezegun.freeze_time('2021-07-12', tick=True)  # tick needed for selenium tests if text not present
@pytest.mark.django_db
def test_see_published_by_others(user_alice_logged_in, user_bob, handle_usage_statistics, settings):
    browser, user_alice = user_alice_logged_in

    # switch off checks for too fast publication
    settings.MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS = None

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
    Topography2DFactory(surface=surface)
    publication = Publication.publish(surface, 'cc0-1.0', 'Bob')

    # Alice filters for published surfaces - enters
    # "Select" tab and chooses "Only published surfaces"
    #
    goto_select_page(browser)

    assert num_items_in_result_table(browser) == 2  # both surfaces are visible by default

    select_sharing_status(browser, 'published_ingress')
    assert num_items_in_result_table(browser) == 1  # only published is visible

    # Bobs surface is visible as only surface.
    # The version number is "1".
    data = data_of_item_by_name(browser, surface_name)
    assert data['description'] == surface_description
    assert data['version'] == "1 (2021-07-12)"

    # Alice opens the properties and sees
    # the "published by Bob" badge.
    press_view_for_item_by_name(browser, surface_name)
    assert browser.is_text_present('published by Bob Marley')

    # She opens the permissions and sees that Everyone has read permissions
    # and nothing else.
    # The individual names are NOT listed.
    assert_only_permissions_everyone(browser)

    #
    # She sees a dropdown with only this version
    #
    assert browser.is_text_present('Version 1')
    assert not browser.is_text_present('Version 2')

    #
    # Bob publishes again, Alice reloads the page
    #
    publication = Publication.publish(surface, 'cc0-1.0', 'Bob')
    browser.reload()

    #
    # Now also the second version is visible
    #
    assert browser.is_text_present('Version 1')
    assert not browser.is_text_present('Version 2')

    #
    # Alice can switch to the new version
    #
    versions_btn = browser.find_by_id('versions-btn')
    versions_btn.click()
    versions_dropdown = browser.find_by_id('versions-dropdown')
    version_links = versions_dropdown.find_by_tag('a')

    assert "Version 1" in version_links[0].text
    assert "Version 2" in version_links[1].text

    version_links[1].click()

    assert browser.is_text_present(f"{publication.original_surface.label}", wait_time=1)

    #
    # Alice should be on the page of the new version
    #
    assert publication.surface.get_absolute_url() in browser.url


@pytest.mark.django_db
def test_switch_between_wip_and_version(user_alice_logged_in, handle_usage_statistics):
    browser, user_alice = user_alice_logged_in

    #
    # Alice has a surface and publishes it
    #
    surface = SurfaceFactory(creator=user_alice, name="Alice's Surface")
    Topography2DFactory(surface=surface)
    publication = Publication.publish(surface, 'cc0-1.0', 'Alice')

    #
    # When browsing to the surface, the current surface is shown as "Work in progress"
    #
    goto_select_page(browser)
    press_view_for_item_by_name(browser, surface.name)

    assert browser.is_text_present("Work in progress")
    assert not browser.is_text_present("Version 1")

    # She could edit, if she wanted
    assert browser.is_text_present("Edit meta data")

    #
    # Switching to version 1
    #
    versions_btn = browser.find_by_id('versions-btn')
    versions_btn.click()
    versions_dropdown = browser.find_by_id('versions-dropdown')
    version_links = versions_dropdown.find_by_tag('a')

    assert "Work in progress" in version_links[0].text
    assert "Version 1" in version_links[1].text

    version_links[1].click()

    assert browser.is_text_present(f"{publication.surface.label}", wait_time=1)

    #
    # Alice should be on the page of the new version
    #
    assert publication.surface.get_absolute_url() in browser.url

    # She cannot edit
    assert not browser.is_text_present("Edit meta data")

    #
    # Alice can switch back to editable version (work in progress)
    #
    versions_btn = browser.find_by_id('versions-btn')
    versions_btn.click()
    versions_dropdown = browser.find_by_id('versions-dropdown')
    version_links = versions_dropdown.find_by_tag('a')

    assert "Work in progress" in version_links[0].text
    assert "Version 1" in version_links[1].text

    version_links[0].click()

    assert browser.is_text_present(f"{publication.original_surface.label}", wait_time=1)
    assert publication.original_surface.get_absolute_url() in browser.url

    assert browser.is_text_present("Edit meta data")


@freezegun.freeze_time('2021-07-12')
@pytest.mark.django_db
def test_how_to_cite(user_alice_logged_in, handle_usage_statistics):
    browser, user_alice = user_alice_logged_in

    #
    # Alice has a surface and publishes it
    #
    surface_name = "Diamond Structure"
    topo_name = "Diamond Cut"
    topo_description = "My nice measurement"

    surface = SurfaceFactory(creator=user_alice, name=surface_name)
    Topography2DFactory(surface=surface, name=topo_name, description=topo_description)
    publication = Publication.publish(surface, 'cc0-1.0', 'Famous Scientist')

    # Alice filters for published surfaces - enters
    # "Select" tab and chooses "Only published surfaces"
    #
    base_url = browser.url
    goto_select_page(browser)

    assert num_items_in_result_table(browser) == 2  # both surfaces are visible by default

    select_sharing_status(browser, 'published_ingress')
    assert num_items_in_result_table(browser) == 1  # only published is visible

    data = data_of_item_by_name(browser, surface_name)
    assert data['version'] == "1 (2021-07-12)"
    assert data['authors'] == 'Famous Scientist'

    double_click_on_item_by_name(browser, surface_name)
    data = data_of_item_by_name(browser, topo_name)
    assert data['version'] == ""
    assert data['authors'] == ''
    assert data['description'] == topo_description

    # Alice opens the properties and sees
    # the "published by yo" badge.
    press_view_for_item_by_name(browser, surface_name)
    assert browser.is_text_present('published by you')

    #
    # Alice sees "How to cite" tab an chooses it
    #
    assert browser.is_text_present("How to cite")
    browser.links.find_by_partial_text("How to cite").click()

    # Now the page shows a citation in text format
    exp_pub_url = base_url.rstrip('/') + publication.get_absolute_url()
    exp_citation = (f"Famous Scientist. ({publication.datetime.year}). contact.engineering. {surface_name} "
                    f"(Version 1). {exp_pub_url}")
    assert browser.is_text_present(exp_citation)

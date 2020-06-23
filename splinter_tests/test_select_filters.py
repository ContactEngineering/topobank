import pytest
from selenium.webdriver.common.keys import Keys

from topobank.manager.tests.utils import SurfaceFactory, TopographyFactory, TagModelFactory, UserFactory


def search_for(browser, search_term):
    browser.fill("search", search_term)
    browser.type("search", Keys.RETURN)
    # TODO wait for select tab is active



def _selected_value(browser, select_css_selector):
    """
    Also checks if exactly one option is selected.

    Parameters
    ----------
    browser
        Splinter browser
    select_css_selector
        CSS selector for the <select> element

    Returns
    -------
    Value of the selected option.
    """
    select = browser.find_by_css(select_css_selector)
    selected_options = select.find_by_css('option:checked')
    assert len(selected_options) == 1
    selected_option = selected_options.first
    return selected_option.value


def selected_category(browser):
    return _selected_value(browser, "div.form-group:nth-child(2) > select:nth-child(1)")


def selected_sharing_status(browser):
    return _selected_value(browser, "div.form-group:nth-child(3) > select:nth-child(1)")


def selected_tree_mode(browser):
    div = browser.find_by_id('tree-selector')
    checked_radio_button = div.find_by_css('input:checked').first
    return checked_radio_button.value


def active_page_number(browser):
    """Returns page number currently active.

    Parameters
    ----------
    browser

    Returns
    -------
    int
    """
    pagination = browser.find_by_id('pagination')
    active_page_items = pagination.find_by_css('li.page-item.active')
    assert len(active_page_items) == 1
    active_page_item = active_page_items.first
    return int(active_page_item.find_by_css('a.page-link').first.text)


def active_page_size(browser):
    return int(_selected_value(browser, "#page-size-select"))


@pytest.fixture(scope='function')
def items_for_filtering(db, user_alice, user_bob):

    tag1 = TagModelFactory(name='tag1')
    tag2 = TagModelFactory(name='tag2')

    surface1 = SurfaceFactory(name='surface1', creator=user_alice, category='exp', description='apple')
    topo1a = TopographyFactory(name='topo1a', surface=surface1)
    topo1b = TopographyFactory(name='topo1b', surface=surface1, tags=[tag1, tag2])

    surface2 = SurfaceFactory(name='surface2', creator=user_alice, category='dum',
                              tags=[tag1], description='banana')
    topo2a = TopographyFactory(name='topo2a', surface=surface2)

    surface3 = SurfaceFactory(name='surface3', creator=user_bob, category='sim', description='cherry')
    topo3a = TopographyFactory(name='topo3a', surface=surface3)

    surface3.share(user_alice)

    return dict(
        tags=[tag1, tag2],
        surfaces=[surface1, surface2, surface3],
        topographies=[topo1a, topo1b, topo2a, topo3a]
    )


@pytest.mark.django_db
def test_filter(browser, user_alice_logged_in, items_for_filtering):

    tag1, tag2 = items_for_filtering['tags']
    surface1, surface2, surface3 = items_for_filtering['surfaces']
    topo1a, topo1b, topo2a, topo3a = items_for_filtering['topographies']

    #
    # navigate to select page
    #
    select_link = browser.find_link_by_partial_text('Select')
    select_link.click()

    # Alice should see three surfaces
    #
    # There should be
    # - no search term,
    # - all categories shown
    # - own and shared surfaces shown
    # - tree should be in "surface list" mode
    # - page 1 shown
    # - page size = 10

    assert browser.is_text_present("Showing 3 surfaces out of 3.")
    assert browser.is_text_present("Not filtered for search term")
    assert selected_category(browser) == 'all'
    assert selected_sharing_status(browser) == 'all'
    assert selected_tree_mode(browser) == 'surface list'
    assert active_page_number(browser) == 1
    assert active_page_size(browser) == 10

    assert browser.is_text_present('surface1')
    assert browser.is_text_present('surface2')
    assert browser.is_text_present('surface3')

    # Now she clicks on category "exp"
    # => only surface 1 should be shown
    browser.select('category', 'exp')

    assert browser.is_text_present("Showing 1 surfaces out of 1.")
    assert browser.is_text_present("Not filtered for search term")
    assert selected_category(browser) == 'exp'
    assert selected_sharing_status(browser) == 'all'
    assert selected_tree_mode(browser) == 'surface list'
    assert active_page_number(browser) == 1
    assert active_page_size(browser) == 10

    assert browser.is_text_present('surface1')
    assert not browser.is_text_present('surface2')
    assert not browser.is_text_present('surface3')

    # Now she clicks on category "sim"
    # => only surface 3 should be shown
    browser.select('category', 'sim')
    assert browser.is_text_present("Showing 1 surfaces out of 1.")
    assert selected_category(browser) == 'sim'

    assert not browser.is_text_present('surface1')
    assert not browser.is_text_present('surface2')
    assert browser.is_text_present('surface3')

    #
    # Now change to 'sharing' tab and back
    # => results should be the same
    select_link = browser.find_link_by_partial_href('sharing')
    select_link.click()
    assert browser.is_text_present("Remove selected shares")

    select_link = browser.find_link_by_partial_text('Select')
    select_link.click()

    assert browser.is_text_present("Showing 1 surfaces out of 1.")
    assert browser.is_text_present("Not filtered for search term")
    assert selected_category(browser) == 'sim'
    assert selected_sharing_status(browser) == 'all'
    assert selected_tree_mode(browser) == 'surface list'
    assert active_page_number(browser) == 1
    assert active_page_size(browser) == 10

    assert not browser.is_text_present('surface1')
    assert not browser.is_text_present('surface2')
    assert browser.is_text_present('surface3')

    # Now show only "own" surfaces. Since only surface 3 is shown
    # and this is shared, no surfaces should be visible
    browser.select('sharing_status', 'own')
    assert browser.is_text_present("Showing 0 surfaces out of 0.")

    # Showing again all categories, two surfaces should show up
    browser.select('category', 'all')
    assert browser.is_text_present("Showing 2 surfaces out of 2.")

    assert browser.is_text_present('surface1')
    assert browser.is_text_present('surface2')
    assert not browser.is_text_present('surface3')

    # # Now back to sharing page, then search for 'surface1'
    # # => only one surface is left, rest of switches should be as before
    # select_link = browser.find_link_by_partial_href('sharing')
    # select_link.click()
    # assert browser.is_text_present("Remove selected shares")
    #
    # browser.fill('search', 'surface1\n')
    #
    # assert browser.is_text_present("Showing 1 surfaces out of 1.")
    # assert browser.is_text_present("Clear filter for issue")
    # assert selected_category(browser) == 'all'
    # assert selected_sharing_status(browser) == 'own'
    # assert selected_tree_mode(browser) == 'surface list'
    # assert active_page_number(browser) == 1
    # assert active_page_size(browser) == 10


@pytest.mark.django_db
def test_search(browser, user_alice_logged_in, items_for_filtering):

    # tag1, tag2 = items_for_filtering['tags']
    # surface1, surface2, surface3 = items_for_filtering['surfaces']
    # topo1a, topo1b, topo2a, topo3a = items_for_filtering['topographies']

    search_for(browser, "surface2")

    assert not browser.is_text_present('surface1')
    assert browser.is_text_present('surface2')
    assert not browser.is_text_present('surface3')

    assert browser.is_text_present("Showing 1 surfaces out of 1.")
    assert browser.is_text_present("Clear filter for")
    assert selected_category(browser) == 'all'
    assert selected_sharing_status(browser) == 'all'
    assert selected_tree_mode(browser) == 'surface list'
    assert active_page_number(browser) == 1
    assert active_page_size(browser) == 10

    #
    # Change to tag tree
    # => only tag1 should be present
    # radio_btn = browser.find_by_id('tag-tree-radio-btn')
    browser.find_by_css('label.btn')[1].click()  # TODO find safer option
    # browser.choose('tree_mode', 'tag tree')

    assert browser.is_text_present('tag1', wait_time=2)
    assert not browser.is_text_present('tag2')
    assert not browser.is_text_present('surface1')
    assert not browser.is_text_present('surface3')

    assert browser.is_text_present("Showing 1 top level tags out of 1.")
    assert browser.is_text_present("Clear filter for")
    assert selected_category(browser) == 'all'
    assert selected_sharing_status(browser) == 'all'
    assert selected_tree_mode(browser) == 'tag tree'
    assert active_page_number(browser) == 1
    assert active_page_size(browser) == 10



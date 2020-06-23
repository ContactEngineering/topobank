import pytest

from topobank.manager.tests.utils import SurfaceFactory, TopographyFactory, TagModelFactory, UserFactory


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

    tag1 = TagModelFactory()
    tag2 = TagModelFactory()

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





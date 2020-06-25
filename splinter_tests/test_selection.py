import pytest

from splinter_tests.utils import checkbox_for_item_by_name, is_in_basket, goto_select_page
from topobank.manager.tests.utils import SurfaceFactory, TopographyFactory, TagModelFactory


@pytest.fixture(scope='function')
def items_for_selection(db, user_alice):

    tag1 = TagModelFactory(name="tag1")
    tag2 = TagModelFactory(name="tag2")

    surface1 = SurfaceFactory(creator=user_alice, name='surface1')
    topo1a = TopographyFactory(surface=surface1, name='topo1a')
    topo1b = TopographyFactory(surface=surface1, tags=[tag1, tag2], name='topo1b')

    surface2 = SurfaceFactory(creator=user_alice, tags=[tag1], name="surface2")
    topo2a = TopographyFactory(surface=surface2, name='topo2a')

    return dict(
        tags=[tag1, tag2],
        surfaces=[surface1, surface2],
        topographies=[topo1a, topo1b, topo2a]
    )


@pytest.mark.django_db
def test_deselect_all(user_alice_logged_in, items_for_selection):

    browser, user_alice = user_alice_logged_in

    #
    # navigate to select page and select sth.
    #
    goto_select_page(browser)
    assert browser.is_text_present('surface1', wait_time=1)

    cb = checkbox_for_item_by_name(browser, 'surface1')
    cb.check()

    # now we have a basket item
    assert is_in_basket(browser, 'surface1')

    # pressing unselect
    browser.click_link_by_id('unselect-all')

    # time.sleep(1)

    # now the basket item is no longer there
    assert not is_in_basket(browser, 'surface1')


@pytest.mark.django_db
def test_select_page_size(user_alice_logged_in):

    browser, user_alice = user_alice_logged_in

    # create a lot of surfaces
    for i in range(11):
        SurfaceFactory(creator=user_alice)

    goto_select_page(browser)

    #
    # pagination should have 2 pages
    #
    pagination = browser.find_by_id("pagination")

    # there should be 4 items: previous, 1, 2, next
    assert browser.is_text_present("Next", wait_time=1)

    page_items = pagination.find_by_css(".page-item")

    assert len(page_items) == 4

    assert page_items[0].text == "Previous"
    assert page_items[1].text == "1"
    assert page_items[2].text == "2"
    assert page_items[3].text == "Next"

    # page size should show "10"
    page_size_select = browser.find_by_id("page-size-select")
    assert page_size_select.find_by_css(".selected").first.text == "10"

    # footer should show total number
    assert browser.is_text_present("Showing 10 surfaces out of 11")

    # press "Next"
    page_items[3].click()

    # now footer shows different text
    assert browser.is_text_present("Showing 1 surfaces out of 11", wait_time=1)

    # select page size 25
    page_size_25_option = page_size_select.find_by_css('option')[1]
    assert page_size_25_option.text == "25"
    page_size_25_option.click()

    # now there is only one page
    assert browser.is_text_present("Next", wait_time=1)
    assert browser.is_text_present("Showing 11 surfaces out of 11", wait_time=1)

    pagination = browser.find_by_id("pagination")
    page_items = pagination.find_by_css(".page-item")

    assert len(page_items) == 3

    assert page_items[0].text == "Previous"
    assert page_items[1].text == "1"
    assert page_items[2].text == "Next"

















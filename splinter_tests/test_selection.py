import pytest
import time

from topobank.manager.tests.utils import SurfaceFactory, TopographyFactory, TagModelFactory

@pytest.fixture
def items_for_selection(user_alice):

    tag1 = TagModelFactory()
    tag2 = TagModelFactory()

    surface1 = SurfaceFactory(creator=user_alice)
    topo1a = TopographyFactory(surface=surface1)
    topo1b = TopographyFactory(surface=surface1, tags=[tag1, tag2])

    surface2 = SurfaceFactory(creator=user_alice, tags=[tag1])
    topo2a = TopographyFactory(surface=surface2)

    return dict(
        tags=[tag1, tag2],
        surfaces=[surface1, surface2],
        topographies=[topo1a, topo1b, topo2a]
    )

def checkbox_for_item_by_name(browser, name):
    node_elems = browser.find_by_xpath(f'//td//span[text()="{name}"]/..')
    checkbox = node_elems.find_by_css('span.fancytree-checkbox').first
    return checkbox


def select_item_by_name(browser, name):
    checkbox = checkbox_for_item_by_name(browser, name)
    checkbox.check()


def is_in_basket(browser, name):
    return not browser.find_by_xpath('//div[@id="basket"]').find_by_xpath(f'//span[text()="{name}"]').is_empty()


@pytest.mark.django_db
def test_deselect_all(browser, user_alice_logged_in, items_for_selection):

    #
    # navigate to select page and select sth.
    #
    select_link = browser.find_link_by_partial_text('Select')
    select_link.click()

    cb = checkbox_for_item_by_name(browser, 'surface-0')
    cb.check()

    # now we have a basket item
    assert is_in_basket(browser, 'surface-0')

    # pressing unselect
    browser.click_link_by_id('unselect-all')

    time.sleep(1)

    # now the basket item is no longer there
    assert not is_in_basket(browser, 'surface-0')





from selenium.webdriver.common.keys import Keys


def search_for(browser, search_term):
    browser.fill("search", search_term)
    browser.type("search", Keys.RETURN)
    browser.is_text_present("Create surface", wait_time=1)


def clear_search_term(browser):
    clear_btn = browser.find_by_id('clear-search-term-btn')
    clear_btn.click()
    assert browser.is_text_present('Not filtered for search term', wait_time=1)


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


def is_text_present_in_result_table(browser, s):
    tree_element = browser.find_by_id('surface-tree')
    elems = tree_element.find_by_text(s)
    return len(elems) > 0


def num_items_in_result_table(browser):
    tree_element = browser.find_by_id('surface-tree')
    rows = tree_element.find_by_css('tr')
    return len(rows) - 1  # substract 1 for header row


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

#
# def select_category(browser, category):
#     assert 'Select' in active_tab_title(browser)
#     browser.choose('category', category)
#     assert selected_category(browser) == category  # needed, it may be not implemented yet
#     # skip loading time
#     assert browser.is_element_not_present_by_text("Please wait", wait_time=1)


def click_select_option(browser, name, value):
    option = browser.find_option_by_value(value)  # does not work on directly on "select" element
    option.click()
    # check whether it is activated
    select = browser.find_by_name(name).first
    assert select.value == value


def select_filter_by_name_and_value(browser, name, value):
    assert 'Find & select' in active_tab_title(browser)
    # browser.choose(name, value)  # does not work
    click_select_option(browser, name, value)
    # skip loading time
    assert browser.is_element_not_present_by_text("Please wait", wait_time=1)


def select_category(browser, category):
    select_filter_by_name_and_value(browser, 'category', category)


def select_sharing_status(browser, sharing_status):
    select_filter_by_name_and_value(browser, 'sharing_status', sharing_status)


def select_tree_mode(browser, mode):
    # radio_btn = browser.find_by_id('tag-tree-radio-btn')
    assert browser.is_text_present('Surface list', wait_time=1)
    if mode == 'tag tree':
        mode_btn = browser.find_by_css('label.btn')[1]  # TODO find safer option
    else:
        mode_btn = browser.find_by_css('label.btn')[0]
    # browser.choose('tree_mode', 'tag tree')  # doesnt work because could not scrolled into view
    mode_btn.click()
    assert browser.is_text_present('top level tags', wait_time=1)


def goto_publications_page(browser):
    link = browser.find_link_by_partial_href('publications')
    link.click()


def goto_sharing_page(browser):
    link = browser.find_link_by_partial_href('sharing')
    link.click()
    assert browser.is_text_present("Remove selected shares", wait_time=1)


def goto_select_page(browser):
    select_link = browser.find_link_by_partial_text('Find & select')
    select_link.click()
    assert browser.is_text_present("Showing")


def checkbox_for_item_by_name(browser, name):
    node_elems = browser.find_by_xpath(f'//td//span[text()="{name}"]/..')
    checkbox = node_elems.find_by_css('span.fancytree-checkbox').first
    return checkbox


def row_for_item_by_name(browser, name):
    item_row = browser.find_by_xpath(f'//td//span[text()="{name}"]/../../..').first
    return item_row


def press_view_for_item_by_name(browser, name):
    item_row = row_for_item_by_name(browser, name)
    props_link = item_row.find_by_css("a").first
    props_link.click()
    assert name in active_tab_title(browser)


def data_of_item_by_name(browser, name):
    """Returns dict with data from select table's row.

    Parameters
    ----------
    browser
        Splinter webdriver
    name
        Name of the item in result table on select tab, e.g. name of a surface

    Returns
    -------
        dict

        { "version": <str, version of item or empty string>,
          "description": <str>
        }
    """
    item_row = row_for_item_by_name(browser, name)
    item_row_texts = [td.text for td in item_row.find_by_css('td')]
    assert len(item_row_texts) == 4
    return dict(version=item_row_texts[1],
                description=item_row_texts[2])


def select_item_by_name(browser, name):
    checkbox = checkbox_for_item_by_name(browser, name)
    checkbox.check()


def is_in_basket(browser, name):
    badges = browser.find_by_id('basket').find_by_css('span.badge')
    # find_by_text does not work as expected and a nested second find_by_xpath not search from
    # previously found node as expected, so this is a workaround

    texts = [b.text for b in badges]

    return name in texts


def active_tab_title(browser):
    active_tab = browser.find_by_css("a.nav-link.active").first
    return active_tab.text

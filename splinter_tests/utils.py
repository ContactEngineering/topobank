from selenium.webdriver.common.keys import Keys


def search_for(browser, search_term):
    browser.fill("search", search_term)
    browser.type("search", Keys.RETURN)
    browser.is_text_present("Create surface", wait_time=1)


def clear_search_term(browser):
    clear_btn = browser.find_by_id('clear-search-term-btn')
    clear_btn.click()
    assert browser.is_text_present('Not filtered for search term', wait_time=1)

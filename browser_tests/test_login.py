
import pytest
from selenium.webdriver import Firefox, Chrome
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support.expected_conditions import staleness_of
from selenium.common.exceptions import NoSuchElementException
from contextlib import contextmanager

from topobank.manager.tests.utils import two_topos

# TODO put this and other common code in conftest.py
@pytest.yield_fixture(scope='session')
def webdriver():
    # driver = Firefox(
    #     executable_path='/home/michael/usr/bin/geckodriver',
    #     firefox_binary='/usr/bin/firefox'
    # )
    driver = Chrome()
    yield driver
    driver.quit()

@contextmanager
def wait_for_page_load(browser, timeout=10):
    old_page = browser.find_element_by_tag_name('html')
    yield
    WebDriverWait(browser, timeout).until(
        staleness_of(old_page)
    )

@pytest.mark.django_db
def test_login_logout(live_server, webdriver, two_topos):

    webdriver.get(live_server.url + '/')

    link = webdriver.find_element_by_partial_link_text("Sign In")
    with wait_for_page_load(webdriver):
        link.click()

    username_input = webdriver.find_element_by_id('id_login')
    username_input.send_keys("testuser")

    username_input = webdriver.find_element_by_id('id_password')
    username_input.send_keys("abcd$1234")

    btn = webdriver.find_element_by_xpath("//button[contains(text(),'Sign In')]")
    with wait_for_page_load(webdriver):
        btn.click()

    #
    # Sign In is no longer there, but Sign Out
    #
    with pytest.raises(NoSuchElementException):
        webdriver.find_element_by_partial_link_text("Sign In")

    link = webdriver.find_element_by_partial_link_text("Sign Out") # only available when signed in

    # Sign Out again..
    with wait_for_page_load(webdriver):
        link.click()
    btn = webdriver.find_element_by_xpath("//button[contains(text(),'Sign Out')]")
    with wait_for_page_load(webdriver):
        btn.click()

    #
    # Sign Out is no longer there, but Sign In
    #
    with pytest.raises(NoSuchElementException):
        webdriver.find_element_by_partial_link_text("Sign Out")

    webdriver.find_element_by_partial_link_text("Sign In")


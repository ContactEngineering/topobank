import os
import os.path
import pytest
from contextlib import contextmanager

from selenium.webdriver import Chrome
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By


@pytest.fixture(scope='session')
def webdriver():
    # driver = Firefox(
    #     executable_path='/home/michael/usr/bin/geckodriver',
    #     firefox_binary='/usr/bin/firefox'
    # ) # firefox does not work currently
    driver = Chrome()
    yield driver
    driver.quit()


@contextmanager
def wait_for_page_load(browser, timeout=10):
    old_page = browser.find_element_by_tag_name('html')
    yield
    WebDriverWait(browser, timeout).until(
        expected_conditions.staleness_of(old_page)
    )


def login_user(webdriver, username, password):
    user_dropwdown = webdriver.find_element_by_id('userDropdown')
    user_dropwdown.click()

    link = webdriver.find_element_by_partial_link_text("Sign In")
    with wait_for_page_load(webdriver):
        link.click()

    username_input = webdriver.find_element_by_id('id_login')
    username_input.send_keys(username)

    username_input = webdriver.find_element_by_id('id_password')
    username_input.send_keys(password)

    btn = webdriver.find_element_by_xpath("//button[contains(text(),'Sign In')]")
    with wait_for_page_load(webdriver):
        btn.click()


def logout_user(webdriver):
    user_dropwdown = webdriver.find_element_by_id('userDropdown')
    user_dropwdown.click()

    webdriver.find_element_by_partial_link_text("Sign Out")  # only available when signed in

    first_logout_link_xpath = "//a[@data-target='#logoutModal']"
    wait = WebDriverWait(webdriver, 10)
    logout_button = wait.until(expected_conditions.element_to_be_clickable((By.XPATH, first_logout_link_xpath)))
    logout_button.click()

    footer_link_xpath = "//div[@class='modal-footer']/a"

    wait = WebDriverWait(webdriver, 10)
    logout_button = wait.until(expected_conditions.element_to_be_clickable((By.XPATH, footer_link_xpath)))

    with wait_for_page_load(webdriver):
        logout_button.click()


@pytest.fixture(scope='function')
def no_surfaces_testuser_signed_in(live_server, webdriver, django_user_model, settings):
    """Initialize a test with a "testuser" and no surfaces + login

    :param live_server:
    :param webdriver:
    :return:
    """
    #
    # Switch media to a dedicated directory
    #
    import tempfile
    with tempfile.TemporaryDirectory(prefix='pytest-django-media-') as tmpdirname:
        settings.MEDIA_ROOT = tmpdirname

        #
        # Create a verified test user
        #
        password = "bar"
        email = "user1@example.org"
        username = email

        user = django_user_model.objects.create_user(username=username, password=password, name="Test User")

        from allauth.account.models import EmailAddress
        EmailAddress.objects.create(user=user, verified=True, email=email)

        #
        # Login this user
        #
        webdriver.get(live_server.url + '/')

        user_dropwdown = webdriver.find_element_by_id('userDropdown')
        user_dropwdown.click()

        link = webdriver.find_element_by_partial_link_text("Sign In")
        with wait_for_page_load(webdriver):
            link.click()

        username_input = webdriver.find_element_by_id('id_login')
        username_input.send_keys(username)

        username_input = webdriver.find_element_by_id('id_password')
        username_input.send_keys(password)

        btn = webdriver.find_element_by_xpath("//button[contains(text(),'Sign In')]")
        with wait_for_page_load(webdriver):
            btn.click()

        #
        # Sign In is no longer there, but Sign Out
        #
        with pytest.raises(NoSuchElementException):
            webdriver.find_element_by_partial_link_text("Sign In")

        #
        # here the test takes place in the test function which uses this fixture
        #
        yield

        #
        # Teardown code
        #
        logout_user(webdriver)

        #
        # Sign Out is no longer there, but Sign In
        #
        user_dropwdown = webdriver.find_element_by_id('userDropdown')
        user_dropwdown.click()

        with pytest.raises(NoSuchElementException):
            webdriver.find_element_by_partial_link_text("Sign Out")

    #
    # temporary media directory is deleted again
    #


@pytest.fixture(scope="function")
def one_empty_surface_testuser_signed_in(no_surfaces_testuser_signed_in, webdriver):
    link = webdriver.find_element_by_link_text("Surfaces")
    link.click()

    link = webdriver.find_element_by_link_text("Add Surface")
    link.click()

    input = webdriver.find_element_by_id("id_name")
    input.send_keys("Surface 1")

    link = webdriver.find_element_by_id("submit-id-save")
    link.click()

    # goto start page
    link = webdriver.find_element_by_link_text("TopoBank")
    link.click()


@pytest.fixture(scope="function")
def surface_1_with_topographies_testuser_logged_in(one_empty_surface_testuser_signed_in, webdriver):
    datafile_paths_prefix = 'topobank/manager/fixtures/'

    data_paths = [os.path.join(datafile_paths_prefix, fn)
                  for fn in ['example3.di', 'example4.txt']]

    #
    # Select surface 1 in order to be able to add a topography
    #
    link = webdriver.find_element_by_link_text("Surfaces")
    with wait_for_page_load(webdriver):
        link.click()
    search_field = webdriver.find_element_by_class_name("select2-search__field")
    search_field.send_keys("Surface 1\n")
    btn = webdriver.find_element_by_id("submit-id-save")
    btn.click()

    for dp in data_paths:
        link = webdriver.find_element_by_link_text("Add topography")
        link.click()

        input = webdriver.find_element_by_id("id_0-datafile")
        input.send_keys(dp)

        # go to step 2
        link = webdriver.find_element_by_id("submit-id-save")
        link.click()

        input = webdriver.find_element_by_id('id_1-measurement_date')
        input.send_keys("2018-02-01")

        # go to step 3
        link = webdriver.find_element_by_id("submit-id-save")
        link.click()

        # finally save
        link = webdriver.find_element_by_id("submit-id-save")
        with wait_for_page_load(webdriver):
            link.click()  # let's wait here, because some data file must be uploaded

        # switch to surface view in order to be able to add another topography
        link = webdriver.find_element_by_link_text("Surface 1")
        with wait_for_page_load(webdriver):
            link.click()

    # remove selection again
    link = webdriver.find_element_by_link_text("Surfaces")
    with wait_for_page_load(webdriver):
        link.click()
    clear_selection_link = webdriver.find_element_by_class_name("select2-selection__clear")
    clear_selection_link.click()

    # goto start page
    link = webdriver.find_element_by_link_text("TopoBank")
    link.click()

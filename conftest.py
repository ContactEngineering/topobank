#
# Common settings and fixtures used with pytest
#
import pytest

from topobank.analysis.functions import register_all

PASSWORD = "secret"

@pytest.fixture
def user_alice(django_user_model):
    username = 'alice'

    user = django_user_model.objects.create_user(username=username, password=PASSWORD, name='Alice Wonderland')
    return user

@pytest.fixture
def user_alice_logged_in(live_server, browser, user_alice):

    #
    # Register all analysis functions
    #
    register_all()

    browser.visit(live_server.url + "/accounts/login")  # we don't want to use ORCID here for testing

    #
    # Logging in
    #
    browser.fill('login', user_alice.username)
    browser.fill('password', PASSWORD)
    btn = browser.find_by_text('Sign In').last
    btn.click()

    yield user_alice

    #
    # Logging out
    #
    browser.find_by_id("userDropdown").click()
    browser.find_by_text("Sign Out").first.click()
    browser.is_element_present_by_text("Ready to Leave?", wait_time=1)
    browser.find_by_text("Sign Out").last.click()

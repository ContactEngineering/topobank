import pytest

PASSWORD = "secret"

@pytest.fixture
def user_alice(django_user_model):
    username = 'alice'

    user = django_user_model.objects.create_user(username=username, password=PASSWORD, name='Alice Wonderland')
    return user

@pytest.fixture
def user_alice_logged_in(live_server, browser, user_alice):
    browser.visit(live_server.url + "/accounts/login")  # we don't want to use ORCID here
    browser.fill('login', user_alice.username)
    browser.fill('password', PASSWORD)
    btn = browser.find_by_text("Sign In")
    btn.click()


def test_login(browser, user_alice_logged_in):

    dropdown = browser.find_by_text('Alice Wonderland')
    dropdown.click()
    logout_link = browser.find_by_text('Sign Out')
    logout_link.click()

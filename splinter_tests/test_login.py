import pytest


@pytest.mark.django_db
def test_login(user_alice_logged_in):
    browser, user_alice = user_alice_logged_in

    assert browser.is_text_present("Welcome to contact.engineering")

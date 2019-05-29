

def test_login(browser, user_alice_logged_in):
    assert browser.is_text_present("Welcome to contact.engineering")



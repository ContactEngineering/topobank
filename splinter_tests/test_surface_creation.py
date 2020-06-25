import pytest


@pytest.mark.django_db
def test_empty_surface(user_alice_logged_in):

    browser, user_alice = user_alice_logged_in

    #
    # navigate to surface list and create surface
    #
    browser.find_link_by_partial_text('Select').first.click()

    assert browser.is_text_present('Create Surface', wait_time=2)

    create_link = browser.find_link_by_partial_text('Create Surface').first
    create_link.click()

    browser.fill('name', 'My first empty surface')

    dummy_data_option = browser.find_by_id('id_id_category_0_3')
    dummy_data_option.click()

    save_link = browser.find_by_id('submit-id-save')
    save_link.click()

    #
    # Navigate back to surface list
    #
    select_link = browser.find_link_by_partial_text('Select').first
    select_link.click()
    assert browser.is_text_present('Create Surface', wait_time=2)

    #
    # Select new surface
    #
    browser.find_link_by_partial_text('Properties').first.click()

    assert browser.is_text_present("Permissions", wait_time=2)
    assert browser.is_text_present("My first empty surface")


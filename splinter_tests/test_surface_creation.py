import pytest

@pytest.mark.django_db
def test_empty_surface(browser, user_alice_logged_in):
    #
    # navigate to surface list and create surface
    #
    surfaces_link = browser.find_link_by_partial_text('Select')
    surfaces_link.click()
    create_link = browser.find_link_by_partial_text('Create Surface')
    create_link.click()

    browser.fill('name', 'My first empty surface')

    dummy_data_option = browser.find_by_id('id_id_category_0_3')
    dummy_data_option.click()

    save_link = browser.find_by_id('submit-id-save')
    save_link.click()

    #
    # Navigate back to surface list
    #
    surfaces_link = browser.find_link_by_partial_text('Select')
    surfaces_link.click()

    #
    # Select new surface
    #
    browser.find_link_by_partial_text('Properties').first.click()

    assert "My first empty surface" in browser.html


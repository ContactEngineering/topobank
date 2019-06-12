
def test_empty_surface(browser, user_alice_logged_in):
    #
    # navigate to surface list and create surface
    #
    surfaces_link = browser.find_link_by_partial_text('Surfaces')
    surfaces_link.click()
    create_link = browser.find_link_by_partial_text('Add Surface')
    create_link.click()

    browser.fill('name', 'My first empty surface')

    dummy_data_option = browser.find_by_id('id_id_category_0_3')
    dummy_data_option.click()

    save_link = browser.find_by_id('submit-id-save')
    save_link.click()

    #
    # Navigate back to surface list
    #
    surfaces_link = browser.find_link_by_partial_text('Surfaces')
    surfaces_link.click()

    #
    # Select new surface
    #
    browser.find_option_by_text('My first empty surface').first.click()

    save_link = browser.find_by_id('submit-id-save')
    save_link.click()

    #
    # Now the link "Open" should be visible
    # and we should be on the detail page for the surface
    #
    browser.find_link_by_partial_text('Open').first.click()

    assert "My first empty surface" in browser.html


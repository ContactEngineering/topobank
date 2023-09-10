"""
Browser test for selection of topographies and functions.
"""

import pytest
import os, os.path

from browser_tests.conftest import wait_for_page_load, logout_user, login_user

from topobank.analysis.models import AnalysisFunction

@pytest.mark.django_db(transaction=False)
def test_selection_synchronize(surface_1_with_topographies_testuser_logged_in, webdriver):

    #
    # Create an analysis function for selection
    #
    func = AnalysisFunction.objects.create(name="Height Distribution")
    func.save()

    #
    # Goto to surface selection, select one surface
    #
    link = webdriver.find_element_by_link_text('Surfaces')
    link.click()

    search_field = webdriver.find_element_by_class_name("select2-search__field")
    search_field.send_keys("example3\n")

    btn = webdriver.find_element_by_id("submit-id-save")
    btn.click()

    #
    # Goto analyses page, check whether selection is only one topography
    #
    link = webdriver.find_element_by_link_text('Analyses')
    with wait_for_page_load(webdriver):
        link.click()

    selection_choices = webdriver.find_elements_by_class_name("select2-selection__choice")

    assert len(selection_choices) == 1
    assert selection_choices[0].text[1:] == "example3.di" # first character is some cross symbol, therefore [1:]

    #
    # Also select full surface
    #
    topo_search_field = webdriver.find_elements_by_class_name("select2-search__field")[0]
    topo_search_field.send_keys("Surface 1\n")

    func_search_field = webdriver.find_elements_by_class_name("select2-search__field")[1]
    func_search_field.send_keys("Height\n")

    btn = webdriver.find_element_by_id("submit-id-save")
    btn.click()

    #
    # Change to Surfaces, there should also be both choices
    # (not normalized)
    #
    link = webdriver.find_element_by_link_text('Surfaces')
    link.click()

    selection_choices = webdriver.find_elements_by_class_name("select2-selection__choice")

    assert len(selection_choices) == 2
    assert selection_choices[1].text[1:] == "example3.di"  # first character is some cross symbol, therefore [1:]
    assert selection_choices[0].text[1:] == "Surface 1"  # first character is some cross symbol, therefore [1:]


@pytest.mark.django_db(transaction=False)
def test_selection_only_own_surfaces_and_topos(live_server, django_user_model,
                                               webdriver):

    webdriver.get(live_server.url + '/')
    for i in [1,2]:
        #
        # Create a another verified test user
        #
        password = "passwd{}".format(i)
        email = "user{}".format(i) + "@example.org"
        username = email

        user = django_user_model.objects.create_user(username=username, password=password, name="Test User")

        from allauth.account.models import EmailAddress
        EmailAddress.objects.create(user=user, verified=True, email=email)

        #
        # Login
        #
        login_user(webdriver, username, password)

        #
        # Create a surface and a topography for this user
        #
        link = webdriver.find_element_by_link_text("Surfaces")
        link.click()

        link = webdriver.find_element_by_link_text("Add Surface")
        link.click()

        input = webdriver.find_element_by_id("id_name")
        surface_name = "Surface 1 of {}".format(user.name)
        input.send_keys(surface_name)

        link = webdriver.find_element_by_id("submit-id-save")
        with wait_for_page_load(webdriver):
            link.click()

        datafile_paths_prefix = 'topobank/manager/fixtures/'
        datafile_paths_prefix = os.path.join(os.getcwd(), datafile_paths_prefix)

        data_paths = [os.path.join(datafile_paths_prefix, fn)
                      for fn in ['example3.di', 'example4.txt']]

        for dp in data_paths:

            link = webdriver.find_element_by_link_text("Add topography")
            link.click()

            input = webdriver.find_element_by_id("id_0-datafile")
            input.send_keys(dp)

            # go to step 2
            link = webdriver.find_element_by_id("submit-id-save")
            link.click()

            input = webdriver.find_element_by_id('id_1-name')
            input.send_keys(" of "+username)

            input = webdriver.find_element_by_id('id_1-measurement_date')
            input.send_keys("2018-02-01")

            # go to step 3
            link = webdriver.find_element_by_id("submit-id-save")
            link.click()

            # finally save
            link = webdriver.find_element_by_id("submit-id-save")
            link.click()

            # topography is saved

            # switch to surface view in order to be able to add another topography
            link = webdriver.find_element_by_link_text("Surface 1")
            link.click()


        #
        # Logout
        #
        if i == 1:
            logout_user(webdriver)
        # keep second user logged in

    #
    # Create an analysis function for selection
    #
    func = AnalysisFunction.objects.create(name="Height Distribution")
    func.save()

    #
    # Goto to surface selection, see if only own stuff
    #
    link = webdriver.find_element_by_link_text('Surfaces')
    with wait_for_page_load(webdriver):
        link.click()

    search_field = webdriver.find_element_by_class_name("select2-search__field")
    search_field.click() # activate results

    search_options = webdriver.find_elements_by_class_name("select2-results__option")

    search_options_texts = [ so.text for so in search_options ]

    assert sorted(search_options_texts) == [
        'Surface 1 of user2', 'example3.di of user2', 'example4.txt of user2',
    ]

    #
    # Goto to analysis selection, see if only own stuff
    #
    link = webdriver.find_element_by_link_text('Analyses')
    link.click()

    search_field = webdriver.find_elements_by_class_name("select2-search__field")[0]
    search_field.click() # activate results

    search_options = webdriver.find_elements_by_class_name("select2-results__option")

    search_options_texts = [ so.text for so in search_options ]

    assert sorted(search_options_texts) == [
        'Surface 1 of user2', 'example3.di of user2', 'example4.txt of user2',
    ]

    logout_user(webdriver)

@pytest.mark.django_db(transaction=False)
def test_show_empty_surface_when_explicitly_selected(one_empty_surface_testuser_signed_in, webdriver):

    link = webdriver.find_element_by_link_text("Surfaces")
    with wait_for_page_load(webdriver):
        link.click()

    # Enter Surface name and press select
    topo_search_field = webdriver.find_elements_by_class_name("select2-search__field")[0]
    topo_search_field.send_keys("Surface 1\n")

    btn = webdriver.find_element_by_id("submit-id-save")
    btn.click()

    #
    # Now "Add topography" button should be shown
    #
    webdriver.find_element_by_link_text("Add topography")











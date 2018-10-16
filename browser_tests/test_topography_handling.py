
import pytest
import os, os.path
from django.urls import reverse
from selenium.common.exceptions import NoSuchElementException


@pytest.mark.django_db
def test_deleting_topography(one_empty_surface_testuser_signed_in, webdriver):

    link = webdriver.find_element_by_link_text("Surfaces")
    link.click()

    datafile_path = 'topobank/manager/fixtures/example3.di'  # choose an existing data file which should work
    datafile_path = os.path.join(os.getcwd(), datafile_path)

    link = webdriver.find_element_by_link_text("Add Topography")

    link.click()

    input = webdriver.find_element_by_id("id_0-datafile")
    input.send_keys(datafile_path)


    # go to step 2
    link = webdriver.find_element_by_id("submit-id-save")
    link.click()

    input = webdriver.find_element_by_id('id_1-name')
    input.send_keys("Test Topography")

    input = webdriver.find_element_by_id('id_1-measurement_date')
    input.send_keys("2018-02-01") # should not be validated on cancel

    # go to step 3
    link = webdriver.find_element_by_id("submit-id-save")
    link.click()

    # finally save
    link = webdriver.find_element_by_id("submit-id-save")
    link.click()

    #
    # Now open topography
    #
    link = webdriver.find_element_by_link_text("Surfaces")
    link.click()

    link = webdriver.find_element_by_link_text("Surface 1")
    link.click()

    #
    # Press delete
    #
    table_row = webdriver.find_element_by_class_name("clickable-table-row")
    table_row.click()

    link = webdriver.find_element_by_link_text("Delete")
    link.click()

    #
    # Topography should not be shown any more
    #
    with pytest.raises(NoSuchElementException):
        webdriver.find_element_by_class_name("clickable-table-row")






@pytest.mark.django_db
def test_cancel_while_creating_topography(one_empty_surface_testuser_signed_in, webdriver):

    link = webdriver.find_element_by_link_text("Surfaces")
    link.click()

    datafile_path = 'topobank/manager/fixtures/example3.di'  # choose an existing data file which should work
    datafile_path = os.path.join(os.getcwd(), datafile_path)


    #
    # First cancel from step 1
    #

    link = webdriver.find_element_by_link_text("Add Topography")
    link.click()

    input = webdriver.find_element_by_id("id_0-datafile")

    input.send_keys(datafile_path)

    # now press "cancel", should return to surface list
    link = webdriver.find_element_by_id("submit-id-cancel")
    link.click()

    assert webdriver.current_url.endswith(reverse('manager:surface-list'))

    #
    # Now cancel from step 2
    #

    link = webdriver.find_element_by_link_text("Add Topography")

    link.click()

    input = webdriver.find_element_by_id("id_0-datafile")

    input.send_keys(datafile_path)

    # now press "cancel", should return to surface list
    link = webdriver.find_element_by_id("submit-id-save")
    link.click()

    # now press "cancel", should return to surface list
    link = webdriver.find_element_by_id("submit-id-cancel")
    link.click()

    assert webdriver.current_url.endswith(reverse('manager:surface-list'))

    #
    # Now cancel from step 3
    #

    link = webdriver.find_element_by_link_text("Add Topography")

    link.click()

    input = webdriver.find_element_by_id("id_0-datafile")
    input.send_keys(datafile_path)

    # go to step 2
    link = webdriver.find_element_by_id("submit-id-save")
    link.click()

    input = webdriver.find_element_by_id('id_1-name')
    input.send_keys("Any name")

    input = webdriver.find_element_by_id('id_1-measurement_date')
    input.send_keys("2018-NONSENSE-01") # should not be validated on cancel

    # go to step 3
    link = webdriver.find_element_by_id("submit-id-save")
    link.click()




    # now press "cancel", should return to surface list
    link = webdriver.find_element_by_id("submit-id-cancel")
    link.click()

    assert webdriver.current_url.endswith(reverse('manager:surface-list'))





import os
import os.path
import pytest

from django.urls import reverse
from selenium.common.exceptions import NoSuchElementException
from browser_tests.conftest import wait_for_page_load


@pytest.mark.django_db
def test_deleting_topography(one_empty_surface_testuser_signed_in, webdriver):
    link = webdriver.find_element_by_link_text("Surfaces")
    with wait_for_page_load(webdriver):
        link.click()

    datafile_path = 'topobank/manager/fixtures/example3.di'  # choose an existing data file which should work
    datafile_path = os.path.join(os.getcwd(), datafile_path)

    #
    # Select surface 1 in order to be able to add a topography
    #
    search_field = webdriver.find_element_by_class_name("select2-search__field")
    search_field.send_keys("Surface 1\n")
    btn = webdriver.find_element_by_id("submit-id-save")
    btn.click()

    link = webdriver.find_element_by_partial_link_text("Add topography")
    link.click()

    input = webdriver.find_element_by_id("id_0-datafile")
    input.send_keys(datafile_path)

    # go to step 2
    link = webdriver.find_element_by_id("submit-id-save")
    link.click()

    input = webdriver.find_element_by_id('id_1-measurement_date')
    input.send_keys("2018-02-01")  # should not be validated on cancel

    # go to step 3
    link = webdriver.find_element_by_id("submit-id-save")
    with wait_for_page_load(webdriver):
        link.click()

    # finally save
    link = webdriver.find_element_by_id("submit-id-save")
    with wait_for_page_load(webdriver):
        link.click()

    #
    # Now open topography
    #
    link = webdriver.find_element_by_link_text("Surfaces")
    with wait_for_page_load(webdriver):
        link.click()

    search_field = webdriver.find_element_by_class_name("select2-search__field")
    search_field.send_keys("Surface 1\n")
    btn = webdriver.find_element_by_id("submit-id-save")
    btn.click()

    #
    # Press delete
    #
    table_row = webdriver.find_element_by_class_name("clickable-table-row")
    table_row.click()

    link = webdriver.find_element_by_link_text("Delete")
    with wait_for_page_load(webdriver):
        link.click()

    #
    # Topography should not be shown any more
    #
    with pytest.raises(NoSuchElementException):
        webdriver.find_element_by_class_name("clickable-table-row")


@pytest.mark.django_db
def test_cancel_while_creating_topography(one_empty_surface_testuser_signed_in, webdriver):
    link = webdriver.find_element_by_link_text("Surfaces")
    with wait_for_page_load(webdriver):
        link.click()

    datafile_path = 'topobank/manager/fixtures/example3.di'  # choose an existing data file which should work
    datafile_path = os.path.join(os.getcwd(), datafile_path)

    #
    # First cancel from step 1
    #
    # Enter Surface name and press select
    topo_search_field = webdriver.find_elements_by_class_name("select2-search__field")[0]
    topo_search_field.send_keys("Surface 1\n")

    btn = webdriver.find_element_by_id("submit-id-save")
    btn.click()

    link = webdriver.find_element_by_link_text("Add topography")
    link.click()

    input = webdriver.find_element_by_id("id_0-datafile")

    input.send_keys(datafile_path)

    # now press "cancel", should return to surface list
    link = webdriver.find_element_by_id("submit-id-cancel")
    link.click()

    assert webdriver.current_url.endswith(reverse('manager:select'))

    #
    # Now cancel from step 2
    #

    link = webdriver.find_element_by_link_text("Add topography")

    link.click()

    input = webdriver.find_element_by_id("id_0-datafile")

    input.send_keys(datafile_path)

    # now press "cancel", should return to surface list
    link = webdriver.find_element_by_id("submit-id-save")
    link.click()

    # now press "cancel", should return to surface list
    link = webdriver.find_element_by_id("submit-id-cancel")
    link.click()

    assert webdriver.current_url.endswith(reverse('manager:select'))

    #
    # Now cancel from step 3
    #

    link = webdriver.find_element_by_link_text("Add topography")

    link.click()

    input = webdriver.find_element_by_id("id_0-datafile")
    input.send_keys(datafile_path)

    # go to step 2
    link = webdriver.find_element_by_id("submit-id-save")
    link.click()

    input = webdriver.find_element_by_id('id_1-name')
    input.send_keys("Any name")

    input = webdriver.find_element_by_id('id_1-measurement_date')
    input.send_keys("2018-NONSENSE-01")  # should not be validated on cancel

    # go to step 3
    link = webdriver.find_element_by_id("submit-id-save")
    link.click()

    # now press "cancel", should return to surface list
    link = webdriver.find_element_by_id("submit-id-cancel")
    link.click()

    assert webdriver.current_url.endswith(reverse('manager:select'))

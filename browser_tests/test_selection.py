"""
Browser test for selection of topographies and functions.
"""

import pytest
from topobank.analysis.models import AnalysisFunction

@pytest.mark.django_db
def test_selection_synchronize(surface_1_with_topographies_testuser_logged_in, webdriver):

    #
    # Create an analysis function for selection
    #
    func = AnalysisFunction.objects.create(pyfunc="height_distribution", automatic=False, name="Height Distribution")
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











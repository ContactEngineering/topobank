
import pytest

from topobank.analysis.models import AnalysisFunction, Analysis
from topobank.manager.models import Surface

@pytest.mark.django_db
def test_grouping_by_function(surface_1_with_topographies_testuser_logged_in, webdriver):


    #
    # Create two analysis functions for selection
    #
    height_func = AnalysisFunction.objects.create(pyfunc="height_distribution", automatic=False, name="Height Distribution")
    height_func.save()
    slope_func = AnalysisFunction.objects.create(pyfunc="slope_distribution", automatic=False, name="Slope Distribution")
    slope_func.save()

    funcs = [height_func, slope_func]
    topos = Surface.objects.get(name="Surface 1").topography_set.all()

    #
    # Create analysis results for all
    #
    import pickle
    for func in funcs:
        for topo in topos:
            a  = Analysis.objects.create(function=func, topography=topo,
                                         args=pickle.dumps(()), kwargs=pickle.dumps({}))
            a.task_state = Analysis.SUCCESS
            xx = list(range(10)) # just to fake some values
            yy = list(range(20))
            a.result = pickle.dumps(dict(
                        name=func.name,
                        scalars=dict(
                            mean_slope=1,
                            rms_slope=0,
                        ),
                        xlabel='x',
                        ylabel='y',
                        series=[
                            dict(name=func.name,
                                 x=xx,
                                 y=yy,
                                 style='k-',
                                 ),
                            dict(name='f',
                                 x=xx,
                                 y=yy,
                                 style='r-',
                                 )
                        ]
            ))
            a.save()



    #
    # Select both analyses functions and the surface
    #
    link = webdriver.find_element_by_link_text("Analyses")
    link.click()

    topo_search_field = webdriver.find_elements_by_class_name("select2-search__field")[0]
    topo_search_field.send_keys("Surface 1\n")

    func_search_field = webdriver.find_elements_by_class_name("select2-search__field")[1]
    func_search_field.send_keys("Height\n")
    func_search_field.send_keys("Slope\n")

    btn = webdriver.find_element_by_id("submit-id-save")
    btn.click()

    #
    # Iterate over cards and check whether the analyses have been grouped
    #
    cards = webdriver.find_elements_by_class_name("card")

    # first card is the select dialog
    assert len(cards) == 3

    # we assume that the functions are also ordered by name
    expected_names = [ 'Height Distribution', 'Slope Distribution']

    for k, card in enumerate(cards[1:]): # iterate over other two

        # check function name of card
        header = card.find_element_by_class_name("card-header")
        assert expected_names[k] in header.text

        # check topography names in footer
        footer = card.find_element_by_class_name("card-footer")

        left_column = footer.find_elements_by_class_name("col-6")[0]

        left_column_labels = left_column.find_elements_by_class_name("form-check-label")
        assert ['example3.di','example4.txt'] == [ l.text for l in left_column_labels ]







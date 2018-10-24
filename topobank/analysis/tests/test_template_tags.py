
from ..templatetags.analysis_tags import analyses_results_urls_list_str

from topobank.analysis.models import Analysis

def test_analyses_results_urls_list_str(mocker):

    mocker.patch('topobank.analysis.models.Analysis', autospec=True)
    analyses = [Analysis(id=i) for i in range(3)] # we just need any id

    reverse = mocker.patch('topobank.analysis.templatetags.analysis_tags.reverse', autospec=True)
    reverse.side_effect = ["/analysis/retrieve/0","/analysis/retrieve/1","/analysis/retrieve/2"]
    # we fake here the outcome of the reverse function, we only want to
    # test the template tag

    s = analyses_results_urls_list_str(analyses)

    assert s=='["/analysis/retrieve/0","/analysis/retrieve/1","/analysis/retrieve/2"]'

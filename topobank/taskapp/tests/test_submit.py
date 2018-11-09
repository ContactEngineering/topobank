import pytest
import pickle

from ..tasks import submit_analysis

from topobank.analysis.models import Analysis
from topobank.analysis.models import AnalysisFunction

@pytest.mark.django_db
def test_submit(mocker):

    # we fake a function in the functions modul which would be built
    # by the eval function
    eval_mock = mocker.patch('builtins.eval')
    eval_mock.return_value = lambda topography, a, b, bins=15, window='hann': None

    mocker.patch('topobank.analysis.models.AnalysisFunction', autospect=True)

    af = AnalysisFunction(name='somefunc')

    mocker.patch('topobank.analysis.models.Analysis.objects.create')

    # just an abbreviation
    def assert_correct_args(expected_kwargs):
        Analysis.objects.create.assert_called_with(function=af,
                                                   topography="t",
                                                   task_state=Analysis.PENDING,
                                                   kwargs=pickle.dumps(expected_kwargs))

    # test case 1
    submit_analysis(af, "t", a=1, b=2)
    assert_correct_args(dict(a=1,
                             b=2,
                             bins=15,
                             window='hann'))


    # test case 2
    submit_analysis(af, "t", 1, 2, bins=10)
    assert_correct_args(dict(a=1,
                             b=2,
                             bins=10,
                             window='hann'))

    # test case 3
    submit_analysis(af, "t", 2, 1, window='hamming', bins=5)
    assert_correct_args(dict(a=2,
                             b=1,
                             bins=5,
                             window='hamming'))

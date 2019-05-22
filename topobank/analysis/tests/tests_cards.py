import pytest

from topobank.manager.tests.utils import TopographyFactory
from .utils import AnalysisFunctionFactory

@pytest.mark.django_db
def test_cards(): # TODO choose better name

    topo1 = TopographyFactory()
    topo2 = TopographyFactory()
    topo3 = TopographyFactory()

    func1 = AnalysisFunctionFactory()
    func2 = AnalysisFunctionFactory()


    assert False, "Do we need this test?"

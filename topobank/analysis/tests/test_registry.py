import pytest

from django.contrib.contenttypes.models import ContentType

from ..views import SimpleCardView, PlotCardView
from ..registry import AnalysisRegistry
from ..functions import topography_analysis_function_for_tests
from topobank.manager.tests.utils import Topography1DFactory
from topobank.manager.models import Topography


@pytest.mark.django_db
def test_analysis_function_implementation():
    reg = AnalysisRegistry()

    ct = ContentType.objects.get_for_model(Topography)

    impl = reg.get_implementation("test", ct)

    assert impl.python_function() == topography_analysis_function_for_tests
    assert impl.get_default_kwargs() == dict(a=1, b="foo", bins=15, window="hann")

    t = Topography1DFactory()
    result = impl.eval(t, a=2, b="bar")
    assert result['comment'] == 'Arguments: a is 2, b is bar, bins is 15 and window is hann'


def test_card_view_class():
    reg = AnalysisRegistry()
    assert reg.get_card_view_class('simple') == SimpleCardView
    assert reg.get_card_view_class('plot') == PlotCardView


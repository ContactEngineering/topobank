import pytest

from ..models import Analysis, AnalysisFunction
from topobank.manager.models import Topography
from topobank.manager.tests.utils import two_topos
import datetime

@pytest.mark.django_db
def test_analysis_times(two_topos):

    import pickle

    analysis = Analysis.objects.create(
            topography=Topography.objects.first(),
            function=AnalysisFunction.objects.first(),
            task_state=Analysis.SUCCESS,
            args=pickle.dumps(()),
            kwargs=pickle.dumps({}),
            start_time=datetime.datetime(2018,1,1,12),
            end_time=datetime.datetime(2018,1,1,13),
        )
    analysis.save()

    assert analysis.start_time == datetime.datetime(2018,1,1,12)
    assert analysis.end_time == datetime.datetime(2018, 1, 1, 13)
    assert analysis.duration() == datetime.timedelta(0, 3600)


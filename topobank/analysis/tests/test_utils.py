import pytest
import pickle
import datetime

from topobank.analysis.models import Analysis, AnalysisFunction
from topobank.analysis.utils import mangle_sheet_name
from topobank.manager.models import Topography
from topobank.manager.tests.utils import two_topos # for fixture


from ..utils import get_latest_analyses

@pytest.mark.django_db
def test_latest_analyses(two_topos, django_user_model):

    topo1 = Topography.objects.get(name="Example 3 - ZSensor")
    topo2 = Topography.objects.get(name="Example 4 - Default")
    af = AnalysisFunction.objects.first()

    # delete all prior analyses for these two topographies in order to have a clean state
    Analysis.objects.filter(topography__in=[topo1,topo2]).delete()

    #
    # Topography 1
    #
    analysis = Analysis.objects.create(
        topography=topo1,
        function=af,
        task_state=Analysis.SUCCESS,
        kwargs=pickle.dumps({}),
        start_time=datetime.datetime(2018, 1, 1, 12),
        end_time=datetime.datetime(2018, 1, 1, 13, 1, 1),
    )
    analysis.save()

    # save a second only, which has a later start time
    analysis = Analysis.objects.create(
        topography=topo1,
        function=af,
        task_state=Analysis.SUCCESS,
        kwargs=pickle.dumps({}),
        start_time=datetime.datetime(2018, 1, 2, 12),
        end_time=datetime.datetime(2018, 1, 2, 13, 1, 1),
    )
    analysis.save()

    #
    # Topography 2
    #
    analysis = Analysis.objects.create(
        topography=topo2,
        function=af,
        task_state=Analysis.SUCCESS,
        kwargs=pickle.dumps({}),
        start_time=datetime.datetime(2018, 1, 3, 12),
        end_time=datetime.datetime(2018, 1, 3, 13, 1, 1),
    )
    analysis.save()

    # save a second one, which has the latest start time
    analysis = Analysis.objects.create(
        topography=topo2,
        function=af,
        task_state=Analysis.SUCCESS,
        kwargs=pickle.dumps({}),
        start_time=datetime.datetime(2018, 1, 5, 12),
        end_time=datetime.datetime(2018, 1, 5, 13, 1, 1),
    )
    analysis.save()

    # save a third one, which has a later start time than the first
    analysis = Analysis.objects.create(
        topography=topo2,
        function=af,
        task_state=Analysis.SUCCESS,
        kwargs=pickle.dumps({}),
        start_time=datetime.datetime(2018, 1, 4, 12),
        end_time=datetime.datetime(2018, 1, 4, 13, 1, 1),
    )
    analysis.save()

    analyses = get_latest_analyses(af.id, [topo1.id, topo2.id])

    assert len(analyses) == 2 # one analysis per function and topography

    # both topographies should be in there
    at1 = analyses.get(topography=topo1)
    at2 = analyses.get(topography=topo2)

    from django.conf import settings

    import pytz

    tz = pytz.timezone(settings.TIME_ZONE)

    assert at1.start_time == tz.localize(datetime.datetime(2018, 1, 2, 12))
    assert at2.start_time == tz.localize(datetime.datetime(2018, 1, 5, 12))

def test_mangle_sheet_name():

    # Not sure, what the real restrictions are. An error message
    # states that e.g. ":" should not be the first or last character,
    # but actually it is also not allowed in the middle?!
    # So we remove them completely.

    assert mangle_sheet_name("RMS height: 19.6 mm") == "RMS height 19.6 mm"
    assert mangle_sheet_name("Right?") == "Right"
    assert mangle_sheet_name("*") == ""


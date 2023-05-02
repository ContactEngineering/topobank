import pytest
import math
import datetime
from django.contrib.contenttypes.models import ContentType

from ...analysis.models import Analysis, AnalysisFunction
from ...analysis.utils import mangle_sheet_name, request_analysis, round_to_significant_digits
from ...analysis.tests.utils import TopographyAnalysisFactory, AnalysisFunctionFactory
from ...manager.models import Topography
from ...manager.tests.utils import UserFactory, two_topos


@pytest.mark.django_db
def test_request_analysis(two_topos, test_analysis_function):
    topo1 = Topography.objects.get(name="Example 3 - ZSensor")
    topo2 = Topography.objects.get(name="Example 4 - Default")

    # delete all prior analyses for these two topographies in order to have a clean state
    Analysis.objects.filter(topography__in=[topo1, topo2]).delete()

    user = UserFactory()

    analysis = request_analysis(user=user, subject=topo1, analysis_func=test_analysis_function)

    assert analysis.subject == topo1
    assert analysis.function == test_analysis_function
    assert user in analysis.users.all()


@pytest.mark.django_db
def test_latest_analyses(two_topos, test_analysis_function):

    topo1 = Topography.objects.get(name="Example 3 - ZSensor")
    topo2 = Topography.objects.get(name="Example 4 - Default")

    user = topo1.creator

    # delete all prior analyses for these two topographies in order to have a clean state
    Analysis.objects.filter(topography__in=[topo1, topo2]).delete()

    #
    # Topography 1
    #
    analysis = TopographyAnalysisFactory.create(
        subject=topo1,
        function=test_analysis_function,
        task_state=Analysis.SUCCESS,
        kwargs={},
        start_time=datetime.datetime(2018, 1, 1, 12),
        end_time=datetime.datetime(2018, 1, 1, 13, 1, 1),
    )
    analysis.save()
    analysis.users.add(user)

    # save a second only, which has a later start time
    analysis = TopographyAnalysisFactory.create(
        subject=topo1,
        function=test_analysis_function,
        task_state=Analysis.SUCCESS,
        kwargs={},
        start_time=datetime.datetime(2018, 1, 2, 12),
        end_time=datetime.datetime(2018, 1, 2, 13, 1, 1),
    )
    analysis.save()
    analysis.users.add(user)

    #
    # Topography 2
    #
    analysis = TopographyAnalysisFactory.create(
        subject=topo2,
        function=test_analysis_function,
        task_state=Analysis.SUCCESS,
        kwargs={},
        start_time=datetime.datetime(2018, 1, 3, 12),
        end_time=datetime.datetime(2018, 1, 3, 13, 1, 1),
    )
    analysis.save()
    analysis.users.add(user)

    # save a second one, which has the latest start time
    analysis = TopographyAnalysisFactory.create(
        subject=topo2,
        function=test_analysis_function,
        task_state=Analysis.SUCCESS,
        kwargs={},
        start_time=datetime.datetime(2018, 1, 5, 12),
        end_time=datetime.datetime(2018, 1, 5, 13, 1, 1),
    )
    analysis.save()
    analysis.users.add(user)

    # save a third one, which has a later start time than the first
    analysis = TopographyAnalysisFactory.create(
        subject=topo2,
        function=test_analysis_function,
        task_state=Analysis.SUCCESS,
        kwargs={},
        start_time=datetime.datetime(2018, 1, 4, 12),
        end_time=datetime.datetime(2018, 1, 4, 13, 1, 1),
    )
    analysis.save()
    analysis.users.add(user)

    tt = ContentType.objects.get_for_model(Topography)
    analyses = get_latest_analyses(user, test_analysis_function, [topo1, topo2])

    assert len(analyses) == 2  # one analysis per function and topography

    # both topographies should be in there

    at1 = analyses.get(subject_type=tt, subject_id=topo1.id)
    at2 = analyses.get(subject_type=tt, subject_id=topo2.id)

    from django.conf import settings

    import pytz

    tz = pytz.timezone(settings.TIME_ZONE)

    assert at1.start_time == tz.localize(datetime.datetime(2018, 1, 2, 12))
    assert at2.start_time == tz.localize(datetime.datetime(2018, 1, 5, 12))


@pytest.mark.django_db
def test_latest_analyses_if_no_analyses(test_analysis_function):
    user = UserFactory()
    assert get_latest_analyses(user, test_analysis_function, []).count() == 0


def test_mangle_sheet_name():
    # Not sure, what the real restrictions are. An error message
    # states that e.g. ":" should not be the first or last character,
    # but actually it is also not allowed in the middle?!
    # So we remove them completely.

    assert mangle_sheet_name("RMS height: 19.6 mm") == "RMS height 19.6 mm"
    assert mangle_sheet_name("Right?") == "Right"
    assert mangle_sheet_name("*") == ""


@pytest.mark.parametrize(['x', 'num_sig_digits', 'rounded'], [
    (49.9999999999999, 1, 50),
    (2.71143412237, 1, 3),
    (2.71143412237, 2, 2.7),
    (2.71143412237, 3, 2.71),
    (2.71143412237, 10, 2.7114341224),
    (-3.45, 2, -3.5),
    (0,5,0),
    (float('nan'), 5, float('nan'))
])
def test_round_to_significant_digits(x, num_sig_digits, rounded):
    if math.isnan(x):
        assert math.isnan(round_to_significant_digits(x, num_sig_digits))
    else:
        assert math.isclose(round_to_significant_digits(x, num_sig_digits), rounded, abs_tol=1e-20)

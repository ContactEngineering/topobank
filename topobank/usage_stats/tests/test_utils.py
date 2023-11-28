import pytest
import datetime

from django.conf import settings

from freezegun import freeze_time

from ...analysis.tests.utils import TopographyAnalysisFactory
from ...manager.tests.utils import Topography1DFactory, SurfaceFactory, UserFactory
from ..utils import increase_statistics_by_date, increase_statistics_by_date_and_object, current_statistics

from topobank_publication.models import Publication


@pytest.mark.skipif(not settings.ENABLE_USAGE_STATS, reason='Usage statistics not enabled')
@pytest.mark.django_db
def test_increase_statistics_by_date(handle_usage_statistics):
    from trackstats.models import Metric, Domain, StatisticByDate

    Domain.objects.TESTDOMAIN = Domain.objects.register(ref='test', name='A test domain')
    Metric.objects.TESTMETRIC = Metric.objects.register(ref='test', name='A test metric',
                                                        domain=Domain.objects.TESTDOMAIN)

    metric = Metric.objects.TESTMETRIC

    today = datetime.date.today()

    increase_statistics_by_date(metric, increment=2)

    s = StatisticByDate.objects.get(metric=metric)
    assert s.value == 2
    assert s.date == today

    increase_statistics_by_date(metric)

    s = StatisticByDate.objects.get(metric=metric)
    assert s.value == 3
    assert s.date == today

    #
    # Fake that a value was increased a day before
    #
    yesterday = today - datetime.timedelta(1)
    with freeze_time(yesterday):
        increase_statistics_by_date(metric)

        s = StatisticByDate.objects.get(metric=metric, date=yesterday)
        assert s.value == 1
        assert s.date == yesterday


@pytest.mark.skipif(not settings.ENABLE_USAGE_STATS, reason='Usage statistics not enabled')
@pytest.mark.django_db
def test_increase_statistics_by_date_and_object(handle_usage_statistics):
    from trackstats.models import Metric, Domain, StatisticByDateAndObject

    Domain.objects.TESTDOMAIN = Domain.objects.register(ref='test', name='A test domain')
    Metric.objects.TESTMETRIC = Metric.objects.register(ref='test', name='A test metric',
                                                        domain=Domain.objects.TESTDOMAIN)

    metric = Metric.objects.TESTMETRIC

    topo1 = Topography1DFactory()
    topo2 = Topography1DFactory()

    today = datetime.date.today()

    #
    # Increase counter for topo1
    #
    increase_statistics_by_date_and_object(metric, obj=topo1, increment=2)

    s = StatisticByDateAndObject.objects.get(metric=metric, object_id=topo1.id)
    assert s.value == 2
    assert s.date == today

    increase_statistics_by_date_and_object(metric, obj=topo1)

    s = StatisticByDateAndObject.objects.get(metric=metric, object_id=topo1.id)
    assert s.value == 3
    assert s.date == today

    #
    # Increase counter for topo2
    #
    increase_statistics_by_date_and_object(metric, obj=topo2)
    s = StatisticByDateAndObject.objects.get(metric=metric, object_id=topo1.id)
    assert s.value == 3
    assert s.date == today
    s = StatisticByDateAndObject.objects.get(metric=metric, object_id=topo2.id)
    assert s.value == 1
    assert s.date == today

    #
    # Fake that a value was increased a day before
    #
    yesterday = today - datetime.timedelta(1)
    with freeze_time(yesterday):
        increase_statistics_by_date_and_object(metric, obj=topo2)
        s = StatisticByDateAndObject.objects.get(metric=metric, object_id=topo2.id, date=yesterday)
        assert s.value == 1
        assert s.date == yesterday


@pytest.fixture
def stats_instances(db, test_analysis_function):
    user_1 = UserFactory()
    user_2 = UserFactory()
    surf_1A = SurfaceFactory(creator=user_1)
    surf_1B = SurfaceFactory(creator=user_1)
    surf_2A = SurfaceFactory(creator=user_2)
    topo_1Aa = Topography1DFactory(surface=surf_1A)
    topo_1Ab = Topography1DFactory(surface=surf_1A)
    topo_1Ba = Topography1DFactory(surface=surf_1B)
    topo_2Aa = Topography1DFactory(surface=surf_2A)

    TopographyAnalysisFactory(subject_topography=topo_1Aa, function=test_analysis_function)
    TopographyAnalysisFactory(subject_topography=topo_1Ab, function=test_analysis_function)
    TopographyAnalysisFactory(subject_topography=topo_2Aa, function=test_analysis_function)

    return user_1, user_2, surf_1A


@pytest.mark.parametrize('with_publication', [False, True])
@pytest.mark.django_db
def test_current_statistics(stats_instances, with_publication):
    user_1, user_2, surf_1A = stats_instances

    if with_publication:
        Publication.publish(surf_1A, 'cc0-1.0', 'Mickey Mouse')

    #
    # statistics without user
    #
    stats = current_statistics()
    assert stats == dict(
        num_surfaces_excluding_publications=3,
        num_topographies_excluding_publications=4,
        num_analyses_excluding_publications=3,
    )

    #
    # statistics for user 1
    #
    stats = current_statistics(user_1)
    assert stats == dict(
        num_surfaces_excluding_publications=2,
        num_topographies_excluding_publications=3,
        num_analyses_excluding_publications=2,
    )

    #
    # statistics for user 2
    #
    stats = current_statistics(user_2)
    assert stats == dict(
        num_surfaces_excluding_publications=1,
        num_topographies_excluding_publications=1,
        num_analyses_excluding_publications=1,
    )

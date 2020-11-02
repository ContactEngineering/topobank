import pytest
import datetime

from freezegun import freeze_time

from topobank.manager.tests.utils import TopographyFactory, SurfaceFactory, UserFactory
from topobank.analysis.tests.utils import AnalysisFactory

from ..utils import increase_statistics_by_date, increase_statistics_by_date_and_object, current_statistics


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


@pytest.mark.django_db
def test_increase_statistics_by_date_and_object(handle_usage_statistics):

    from trackstats.models import Metric, Domain, StatisticByDateAndObject

    Domain.objects.TESTDOMAIN = Domain.objects.register(ref='test', name='A test domain')
    Metric.objects.TESTMETRIC = Metric.objects.register(ref='test', name='A test metric',
                                                        domain=Domain.objects.TESTDOMAIN)

    metric = Metric.objects.TESTMETRIC

    topo1 = TopographyFactory()
    topo2 = TopographyFactory()

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
def stats_instances(db):
    user_1 = UserFactory()
    user_2 = UserFactory()
    surf_1A = SurfaceFactory(creator=user_1)
    surf_1B = SurfaceFactory(creator=user_1)
    surf_2A = SurfaceFactory(creator=user_2)
    topo_1Aa = TopographyFactory(surface=surf_1A)
    topo_1Ab = TopographyFactory(surface=surf_1A)
    topo_1Ba = TopographyFactory(surface=surf_1B)
    topo_2Aa = TopographyFactory(surface=surf_2A)
    AnalysisFactory(topography=topo_1Aa)
    AnalysisFactory(topography=topo_1Ab)
    AnalysisFactory(topography=topo_2Aa)

    return user_1, user_2, surf_1A


@pytest.mark.parametrize('with_publication', [False, True])
@pytest.mark.django_db
def test_current_statistics(stats_instances, with_publication):

    user_1, user_2, surf_1A = stats_instances

    if with_publication:
        surf_1A.publish('cc0-1.0', 'Mickey Mouse')

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

import pytest
import datetime

from freezegun import freeze_time

from topobank.manager.tests.utils import TopographyFactory

from ..utils import increase_statistics_by_date, increase_statistics_by_date_and_object


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

import pytest
from topobank.manager.tests.utils import TopographyFactory

from ..utils import increase_statistics_by_date, increase_statistics_by_date_and_object

@pytest.mark.django_db
def test_increase_statistics_by_date(handle_usage_statistics):

    from trackstats.models import Metric, Domain, StatisticByDate

    Domain.objects.TESTDOMAIN = Domain.objects.register(ref='test', name='A test domain')
    Metric.objects.TESTMETRIC = Metric.objects.register(ref='test', name='A test metric',
                                                        domain=Domain.objects.TESTDOMAIN)

    metric = Metric.objects.TESTMETRIC


    increase_statistics_by_date(metric, increment=2)

    s = StatisticByDate.objects.get(metric=metric)
    assert s.value == 2

    increase_statistics_by_date(metric)

    s = StatisticByDate.objects.get(metric=metric)
    assert s.value == 3


@pytest.mark.django_db
def test_increase_statistics_by_date_and_object(handle_usage_statistics):

    from trackstats.models import Metric, Domain, StatisticByDateAndObject

    Domain.objects.TESTDOMAIN = Domain.objects.register(ref='test', name='A test domain')
    Metric.objects.TESTMETRIC = Metric.objects.register(ref='test', name='A test metric',
                                                        domain=Domain.objects.TESTDOMAIN)

    metric = Metric.objects.TESTMETRIC

    topo1 = TopographyFactory()
    topo2 = TopographyFactory()

    #
    # Increase counter for topo1
    #
    increase_statistics_by_date_and_object(metric, obj=topo1, increment=2)

    s = StatisticByDateAndObject.objects.get(metric=metric, object_id=topo1.id)
    assert s.value == 2

    increase_statistics_by_date_and_object(metric, obj=topo1)

    s = StatisticByDateAndObject.objects.get(metric=metric, object_id=topo1.id)
    assert s.value == 3

    #
    # Increase counter for topo2
    #
    increase_statistics_by_date_and_object(metric, obj=topo2)
    s = StatisticByDateAndObject.objects.get(metric=metric, object_id=topo1.id)
    assert s.value == 3
    s = StatisticByDateAndObject.objects.get(metric=metric, object_id=topo2.id)
    assert s.value == 1


import pytest
import datetime
from freezegun import freeze_time
from django.shortcuts import reverse

from trackstats.models import Metric, Period

@pytest.mark.skip
@pytest.mark.django_db
def test_total_request_counts(client, mocker, handle_usage_statistics):

    metric = Metric.objects.TOTAL_REQUEST_COUNT

    record_mock = mocker.patch('trackstats.models.StatisticByDate.objects.record')

    response = client.get(reverse('home'))

    today = datetime.date.today()

    record_mock.assert_called_with(metric=metric, period=Period.DAY,
                                   value=1, date=today)

    response = client.get(reverse('home'))
    assert response.status_code == 200

    assert record_mock.call_count == 2

    #
    # Fake request from yesterday
    #
    yesterday = today - datetime.timedelta(1)
    with freeze_time(yesterday):
        response = client.get(reverse('home'))
        assert response.status_code == 200
        assert record_mock.call_count == 3
        record_mock.assert_called_with(metric=metric, period=Period.DAY,
                                       value=1, date=yesterday)


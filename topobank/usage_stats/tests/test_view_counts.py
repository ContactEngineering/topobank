import pytest
import datetime
from freezegun import freeze_time
from django.shortcuts import reverse

from trackstats.models import Metric, Period

from topobank.analysis.tests.utils import TopographyAnalysisFactory, AnalysisFunctionFactory


@pytest.mark.django_db
def test_counts_analyses_views(client, test_analysis_function, mocker, handle_usage_statistics):

    analysis = TopographyAnalysisFactory.create(function=test_analysis_function)
    topography = analysis.subject
    user = topography.surface.creator

    metric = Metric.objects.ANALYSES_RESULTS_VIEW_COUNT

    client.force_login(user)

    # we have to test here with the 'analysis:card' URL because
    # the views the user sees, load that URL via ajax which is not executed
    # during this test - so we must imitate the AJAX call here
    def send_card_request():
        response = client.post(reverse('analysis:card'), data={
            'function_id': test_analysis_function.id,
            'card_id': 'card',
            'template_flavor': 'list',
            'subjects_ids_json': [topography],
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')  # we need an AJAX request
        return response

    record_mock = mocker.patch('trackstats.models.StatisticByDateAndObject.objects.record')

    response = send_card_request()  # first send request, then request metrics! Otherwise it does not exist.
    assert response.status_code == 200

    today = datetime.date.today()

    record_mock.assert_called_with(metric=metric, object=test_analysis_function,
                                   period=Period.DAY,
                                   value=1, date=today)
    response = send_card_request()
    assert response.status_code == 200

    assert record_mock.call_count == 2

    #
    # Fake request from yesterday
    #
    yesterday = today - datetime.timedelta(1)
    with freeze_time(yesterday):
        response = send_card_request()
        assert response.status_code == 200
        assert record_mock.call_count == 3
        record_mock.assert_called_with(metric=metric, object=test_analysis_function,
                                       period=Period.DAY,
                                       value=1, date=yesterday)

    client.logout()


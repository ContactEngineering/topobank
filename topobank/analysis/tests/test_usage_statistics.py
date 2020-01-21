import pytest
from django.shortcuts import reverse
from trackstats.models import Metric, Period

from topobank.analysis.tests.utils import AnalysisFactory

@pytest.mark.django_db
def test_counts_analyses_views(client, mocker, handle_usage_statistics):
    analysis = AnalysisFactory()
    topography = analysis.topography
    function = analysis.function
    user = analysis.topography.surface.creator

    metric = Metric.objects.ANALYSES_RESULTS_VIEW_COUNT

    client.force_login(user)

    # we have to test here with the 'analysis:card' URL because
    # the views the user sees, load that URL via ajax which is not executed
    # during this test - so we must imitate the AJAX call here
    def send_card_request():
        response = client.get(reverse('analysis:card'), data={
            'function_id': function.id,
            'card_id': 'card',
            'template_flavor': 'list',
            'topography_ids[]': [topography.id],
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')  # we need an AJAX request
        return response

    record_mock = mocker.patch('trackstats.models.StatisticByDateAndObject.objects.record')

    response = send_card_request()  # first send request, then request metrics! Otherwise it does not exist.
    assert response.status_code == 200

    record_mock.assert_called_with(metric=metric, object=function, period=Period.DAY, value=1)
    response = send_card_request()
    assert response.status_code == 200

    assert record_mock.call_count == 2

    client.logout()


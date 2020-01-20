import pytest
from django.shortcuts import reverse
from django.contrib.contenttypes.models import ContentType
from trackstats.models import Metric, StatisticByDateAndObject

from topobank.analysis.tests.utils import AnalysisFactory

@pytest.mark.django_db
def test_counts_analyses_views(client, handle_usage_statistics):
    analysis = AnalysisFactory()
    topography = analysis.topography
    function = analysis.function
    user = analysis.topography.surface.creator

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

    response = send_card_request()  # first send request, then request metrics! Otherwise it does not exist.
    assert response.status_code == 200

    metric = Metric.objects.get(ref='analyses_results_view_count')
    ct = ContentType.objects.get(app_label='analysis', model='analysisfunction')

    def get_function_view_entries():
        return StatisticByDateAndObject.objects.filter(metric=metric,
                                                       object_id=function.id,
                                                       object_type_id=ct.id)


    assert get_function_view_entries().count() == 1

    response = send_card_request()
    assert response.status_code == 200
    assert get_function_view_entries().count() == 2

    client.logout()

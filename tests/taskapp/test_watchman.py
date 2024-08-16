import json

from django.shortcuts import reverse
from watchman.views import status as watchman_status


def test_celery_status_available(rf):
    """Check whether there is celery information in the watchman status."""
    request = rf.get(reverse('watchman:status'))
    response = watchman_status(request)
    json_data = json.loads(response.content)

    # 'celery' should be included, because there is an extra check
    # configured for watchman in the settings, see WATCHMAN_CHECKS
    assert 'celery' in json_data.keys()

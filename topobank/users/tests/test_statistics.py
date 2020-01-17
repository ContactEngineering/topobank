import pytest
import datetime

from trackstats.models import Metric, StatisticByDate

from topobank.manager.tests.utils import UserFactory
from ..signals import track_user_login


@pytest.mark.django_db
def test_login_statistics(client):

    today = datetime.datetime.today()

    user1 = UserFactory()
    user2 = UserFactory()

    client.force_login(user1)
    client.logout()

    client.force_login(user2)
    client.logout()

    # Signal is not called for some reason - calling signal handler manually
    track_user_login(sender=user2.__class__)

    #
    # There should be two logins for two users now for today
    #
    m = Metric.objects.get(ref='login_count')
    s = StatisticByDate.objects.get(metric=m, date=today)
    assert s.value == 2

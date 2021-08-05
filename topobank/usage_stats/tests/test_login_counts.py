import pytest
import datetime
from freezegun import freeze_time

from trackstats.models import Metric, StatisticByDate

from topobank.manager.tests.utils import UserFactory
from topobank.users.signals import track_user_login


@pytest.mark.django_db
def test_login_statistics(client):

    today = datetime.date.today()

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
    m = Metric.objects.USERS_LOGIN_COUNT
    s = StatisticByDate.objects.get(metric=m, date=today)
    assert s.value == 2

    #
    # Check also for a specific day
    #
    yesterday = today - datetime.timedelta(1)

    with freeze_time(yesterday):
        client.force_login(user1)
        client.logout()
        track_user_login(sender=user1.__class__)

        #
        # There should be one login for one user for yesterday
        #
        s = StatisticByDate.objects.get(metric=m, date=yesterday)
        assert s.value == 1

        #
        # There should be still those logins from today
        #
        s = StatisticByDate.objects.get(metric=m, date=today)
        assert s.value == 2

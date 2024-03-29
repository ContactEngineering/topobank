from allauth.account.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.timezone import now
from trackstats.models import Metric, Period, StatisticByDate

from .models import User
from .utils import get_default_group


@receiver(post_save, sender=User)
def add_to_default_group(sender, instance, created, **kwargs):
    if created:
        instance.groups.add(get_default_group())


@receiver(user_logged_in)
def track_user_login(sender, today=None, **kwargs):
    from topobank.users.models import User

    if today is None:
        today = now().date()
    num_users_today = User.objects.filter(
        last_login__year=today.year,
        last_login__month=today.month,
        last_login__day=today.day,
    ).count()
    # since only one "last_login" is saved per user
    # at most one login is counted per user

    StatisticByDate.objects.record(
        metric=Metric.objects.USERS_LOGIN_COUNT,
        value=num_users_today,
        period=Period.DAY
    )

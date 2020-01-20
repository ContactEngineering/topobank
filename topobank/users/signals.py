
from allauth.account.signals import user_signed_up, user_logged_in
from django.dispatch import receiver
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.files import File
from django.shortcuts import reverse
from django.utils.timezone import now

from trackstats.models import StatisticByDate, Metric, Period
from notifications.signals import notify

import os.path
import yaml

from topobank.manager.models import Surface, Topography


@receiver(user_signed_up)
def create_example_surface(sender, **kwargs):

    user = kwargs['user']

    example_info_fn = staticfiles_storage.path('data/example_surface.yaml')
    example_info = yaml.safe_load(open(example_info_fn))

    #
    # Create surface
    #
    surface = Surface.objects.create(creator=user, name=example_info['name'],
                                     description=example_info['description'],
                                     category=example_info['category'])

    #
    # Create topographies and trigger analyses
    #
    for topo_info in example_info['topographies']:

        topo_kwargs = topo_info.copy()
        del topo_kwargs['static_filename']

        # TODO this is a workaround for GH 132 - maybe we don't need to make sizes fixed?
        topo_kwargs['size_editable'] = True

        # TODO Workaround, maybe we don't need height scale restriction
        topo_kwargs['height_scale_editable'] = True

        topo = Topography(surface=surface, **topo_kwargs)

        abs_fn = staticfiles_storage.path(topo_info['static_filename'])
        file = open(abs_fn, 'rb')  # we need binary mode for boto3 (S3 library)

        topo.datafile.save(os.path.basename(abs_fn), File(file))

        topo.save()

        topo.renew_analyses()

    #
    # Notify user
    #
    notify.send(sender=surface, verb="create", target=surface,
                recipient=user,
                description="An example surface has been created for you. Click here to have a look.",
                href=reverse('manager:surface-detail', kwargs=dict(pk=surface.pk)))


@receiver(user_logged_in)
def track_user_login(sender, **kwargs):

    from topobank.users.models import User

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



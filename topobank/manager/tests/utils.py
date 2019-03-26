import pytest
from django.core.management import call_command
from django.conf import settings
from shutil import copyfile
import os.path
import logging

from topobank.users.models import User

_log = logging.getLogger(__name__)

# TODO think about replacing this fixture with factory boy, probably much simpler?!
@pytest.fixture
def two_topos(django_db_setup, django_db_blocker):

    #
    # Copy uploaded files at the correct places
    #
    # This is hack, maybe better to use sth like
    # https://github.com/duncaningram/django-fixture-media
    #
    from_to = [ ('topobank/manager/fixtures/example4.txt',
                 ['topographies/user_1/example4.txt',
                  'topographies/user_1/example4_DiVRsr9.txt']),
                ('topobank/manager/fixtures/example3.di',
                 ['topographies/user_1/example3_K7Ijorz.di'])
    ]

    for from_path, to_paths in from_to:
        from_path = os.path.join(str(settings.ROOT_DIR), from_path)
        for to_path in to_paths:
            to_path = os.path.join(settings.MEDIA_ROOT, to_path)
            _log.info("Copying fixture file '{}' -> '{}'..".format(from_path, to_path))
            copyfile(from_path, to_path)

    #
    # Load database from YAML file
    #
    with django_db_blocker.unblock():
        call_command('loaddata', 'two_topographies.yaml')

        # Fix the passwords of fixtures
        for user in User.objects.all():
            user.set_password(user.password)
            user.save()

        # like this we can have clear-text passwords in test fixtures

import datetime
import factory
from ..models import Topography, Surface
from topobank.users.tests.factories import UserFactory

class SurfaceFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = Surface

    name = factory.Sequence(lambda n: "surface-{}".format(n))
    user = factory.SubFactory(UserFactory)

class TopographyFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = Topography

    surface = factory.SubFactory(SurfaceFactory)
    name = factory.Sequence(lambda n: "topography-{}".format(n))
    data_source = 0
    measurement_date = factory.Sequence(lambda n: datetime.date(2019,1,1)+datetime.timedelta(days=n))

@pytest.fixture
def one_line_scan(django_db_setup):

    user = UserFactory(username='testuser', password='abcd$1234')
    surface = Surface(name="Line Scans", user=user)
    surface.save()

    datafile = factory.django.FileField(from_path="topobank/manager/fixtures/line_scan_1.asc")

    TopographyFactory(surface=surface,
                      name='Simple Line Scan',
                      measurement_date=datetime.date(2018,1,1),
                      description="description1",
                      size_x=9,
                      detrend_mode='height',
                      datafile=datafile)


def export_reponse_as_html(response, fname='/tmp/response.html'):
    """
    Helper function which can be used for debugging.

    :param response: HTTPResponse
    :param fname: name of HTML output file
    """
    f = open(fname, mode='w')

    f.write(response.content.decode('utf-8').replace('\\n','\n'))
    f.close()

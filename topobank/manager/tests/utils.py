import pytest
from django.core.management import call_command
from django.conf import settings
from shutil import copyfile
import os.path
import logging
import datetime
import factory

from ..models import Topography, Surface
from topobank.users.tests.factories import UserFactory
from topobank.users.models import User
from topobank.analysis.functions import register_all

_log = logging.getLogger(__name__)

#
# Define factories for creating test objects
#
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
    datafile = factory.django.FileField(from_path=str(settings.ROOT_DIR.path("topobank/manager/fixtures/10x10.txt")))
    data_source = 0
    measurement_date = factory.Sequence(lambda n: datetime.date(2019,1,1)+datetime.timedelta(days=n))
    size_x = 512
    size_y = None # set this if you need a 2D topography
    size_editable = True
    unit_editable = True
    height_scale_editable = True

#
# Define fixtures
#
@pytest.fixture
def two_topos():

    #with django_db_blocker.unblock():
    call_command('register_analysis_functions')

    user = UserFactory(username='testuser', password='abcd$1234')
    surface = SurfaceFactory(name="Surface 1", user=user)

    datafile1 = factory.django.FileField(from_path="topobank/manager/fixtures/example3.di")
    datafile2 = factory.django.FileField(from_path="topobank/manager/fixtures/example4.txt")

    TopographyFactory(surface=surface,
                      name='Example 3 - ZSensor',
                      data_source=0,
                      measurement_date=datetime.date(2018, 1, 1),
                      description="description1",
                      size_x=10.0,
                      size_y=10.0,
                      unit='µm',
                      detrend_mode='height',
                      height_scale=0.296382712790741,
                      datafile=datafile1,
                      resolution_x=256,
                      resolution_y=256)

    TopographyFactory(surface=surface,
                      name='Example 4 - Default',
                      data_source=0,
                      measurement_date=datetime.date(2018, 1, 2),
                      description="description2",
                      size_x=112.80791,
                      size_y=27.73965,
                      unit='µm',
                      detrend_mode='height',
                      height_scale=2.91818e-08,
                      datafile=datafile2,
                      resolution_x=305,
                      resolution_y=75)


@pytest.fixture
def one_line_scan():

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

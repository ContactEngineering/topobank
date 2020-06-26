import json
from operator import itemgetter

import pytest
from django.core.management import call_command
from django.conf import settings
from shutil import copyfile
import os.path
import logging
import datetime
import factory

from ..models import Topography, Surface, TagModel
from topobank.users.tests.factories import UserFactory
from topobank.users.models import User
from topobank.analysis.functions import register_all


FIXTURE_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    '../fixtures'
)

_log = logging.getLogger(__name__)


#
# Define factories for creating test objects
#
class SurfaceFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = Surface

    name = factory.Sequence(lambda n: "surface-{}".format(n))
    creator = factory.SubFactory(UserFactory)


class TopographyFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = Topography

    surface = factory.SubFactory(SurfaceFactory)
    # creator is set automatically to surface's creator if not set, see signals
    name = factory.Sequence(lambda n: "topography-{}".format(n))
    datafile = factory.django.FileField(from_path=str(settings.ROOT_DIR.path(FIXTURE_DIR+"/10x10.txt")))
    data_source = 0
    measurement_date = factory.Sequence(lambda n: datetime.date(2019, 1, 1)+datetime.timedelta(days=n))
    size_x = 512
    size_y = None  # set this if you need a 2D topography
    size_editable = True
    unit_editable = True
    height_scale_editable = True
    unit = 'nm'


class TagModelFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TagModel
    name = factory.Sequence(lambda n: "tag-{}".format(n))


#
# Define fixtures
#
@pytest.fixture
def two_topos():

    call_command('register_analysis_functions')

    user = UserFactory(username='testuser', password='abcd$1234')
    surface1 = SurfaceFactory(name="Surface 1", creator=user)
    surface2 = SurfaceFactory(name="Surface 2", creator=user)

    datafile1 = factory.django.FileField(from_path=FIXTURE_DIR+"/example3.di")
    datafile2 = factory.django.FileField(from_path=FIXTURE_DIR+"/example4.txt")

    topos1 = TopographyFactory(surface=surface1,
                               creator=user,
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

    topos2 = TopographyFactory(surface=surface2,
                               creator=user,
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
    return topos1, topos2


@pytest.fixture
def one_line_scan():

    user = UserFactory(username='testuser', password='abcd$1234')
    surface = Surface(name="Line Scans", creator=user)
    surface.save()

    datafile = factory.django.FileField(from_path=FIXTURE_DIR+"/line_scan_1.asc")

    return TopographyFactory(surface=surface,
                             name='Simple Line Scan',
                             measurement_date=datetime.date(2018, 1, 1),
                             description="description1",
                             size_x=9,
                             detrend_mode='height',
                             datafile=datafile)


def export_reponse_as_html(response, fname='/tmp/response.html'):  # pragma: no cover
    """
    Helper function which can be used for debugging.

    :param response: HTTPResponse
    :param fname: name of HTML output file
    """
    f = open(fname, mode='w')

    f.write(response.content.decode('utf-8').replace('\\n', '\n'))
    f.close()


def ordereddicts_to_dicts(input_ordered_dict, sorted_by='pk'):
    result = json.loads(json.dumps(input_ordered_dict))
    if sorted_by is not None:
        result = sorted(result, key=itemgetter(sorted_by))
    return result


@pytest.fixture
def topography_with_broken_pyco_topography():
    topo = TopographyFactory()

    from django.core.files.base import ContentFile
    new_content = ContentFile('\x00')  # some nonsense which cannot be interpreted by PyCo
    fname = topo.datafile.name
    topo.datafile.save(fname, new_content)

    return topo


@pytest.fixture
def user_three_topographies_three_surfaces_three_tags():

    user = UserFactory()

    tag1 = TagModelFactory()
    tag2 = TagModelFactory()
    tag3 = TagModelFactory()

    surface1 = SurfaceFactory(creator=user, tags=[tag1])
    topo1a = TopographyFactory(surface=surface1)
    topo1b = TopographyFactory(surface=surface1, tags=[tag2, tag3])

    surface2 = SurfaceFactory(creator=user, tags=[tag2])
    topo2a = TopographyFactory(surface=surface2, tags=[tag1])

    surface3 = SurfaceFactory(creator=user, tags=[tag3])  # empty

    return user, (topo1a, topo1b, topo2a), (surface1, surface2, surface3), (tag1, tag2, tag3)

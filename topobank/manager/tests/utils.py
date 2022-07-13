import json
import tempfile
from operator import itemgetter

import pytest
from django.core.management import call_command
from django.conf import settings

import os.path
import logging
import datetime
import factory

from ..models import Topography, Surface, TagModel
from topobank.users.tests.factories import UserFactory


FIXTURE_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    '../fixtures'
)

_log = logging.getLogger(__name__)


#
# Define factories for creating test objects
#
class SurfaceFactory(factory.django.DjangoModelFactory):
    """Generates a Surface."""

    class Meta:
        model = Surface

    name = factory.Sequence(lambda n: "surface-{:05d}".format(n))  # format because of defined order by name
    creator = factory.SubFactory(UserFactory)


class Topography1DFactory(factory.django.DjangoModelFactory):
    """
    Generates a 1D Topography.
    """

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = Topography

    surface = factory.SubFactory(SurfaceFactory)
    # creator is set automatically to surface's creator if not set, see signals
    name = factory.Sequence(lambda n: "topography-{:05d}".format(n))
    datafile = factory.django.FileField(from_path=str(settings.ROOT_DIR.path(FIXTURE_DIR + "/line_scan_1.asc")))
    data_source = 0
    measurement_date = factory.Sequence(lambda n: datetime.date(2019, 1, 1) + datetime.timedelta(days=n))
    size_x = 512
    # if you need size_y, use Topography2DFactory below
    size_editable = False
    unit_editable = False
    height_scale_editable = True
    unit = 'nm'
    instrument_name = ""
    instrument_type = Topography.INSTRUMENT_TYPE_UNDEFINED
    instrument_parameters = {}


class Topography2DFactory(Topography1DFactory):
    """
    Generates a 2D Topography.
    """
    size_y = 512
    datafile = factory.django.FileField(from_path=str(settings.ROOT_DIR.path(FIXTURE_DIR + "/10x10.txt")))

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = Topography


class TagModelFactory(factory.django.DjangoModelFactory):
    """Generates a tag."""

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

    datafile1 = factory.django.FileField(from_path=FIXTURE_DIR + "/example3.di")
    datafile2 = factory.django.FileField(from_path=FIXTURE_DIR + "/example4.txt")

    topos1 = Topography2DFactory(surface=surface1,
                                 creator=user,
                                 name='Example 3 - ZSensor',
                                 data_source=0,
                                 measurement_date=datetime.date(2018, 1, 1),
                                 description="description1",
                                 size_x=10.0,
                                 size_y=10.0,
                                 size_editable=True,  # needed for tests
                                 unit='µm',
                                 detrend_mode='height',
                                 height_scale_editable=False,  # height_scale_factor defined in DI file
                                 height_scale=0.296382712790741,  # workaround: mentioned here so it is correctly set
                                 # normally this would be set during the upload process
                                 datafile=datafile1,
                                 resolution_x=256,
                                 resolution_y=256)

    topos2 = Topography2DFactory(surface=surface2,
                                 creator=user,
                                 name='Example 4 - Default',
                                 data_source=0,
                                 measurement_date=datetime.date(2018, 1, 2),
                                 description="description2",
                                 size_x=112.80791,
                                 size_y=27.73965,
                                 unit='µm',
                                 detrend_mode='height',
                                 height_scale=2.91818e-08,  # workaround: mentioned here so it is correctly set
                                 height_scale_editable=False,  # defined in TXT file
                                 datafile=datafile2,
                                 resolution_x=305,
                                 resolution_y=75)
    return topos1, topos2


@pytest.fixture
def one_line_scan():
    user = UserFactory(username='testuser', password='abcd$1234')
    surface = Surface(name="Line Scans", creator=user)
    surface.save()

    datafile = factory.django.FileField(from_path=FIXTURE_DIR + "/line_scan_1.asc")

    return Topography1DFactory(surface=surface,
                               name='Simple Line Scan',
                               measurement_date=datetime.date(2018, 1, 1),
                               description="description1",
                               size_x=9,
                               size_editable=True,  # needed for test
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
def topography_loaded_from_broken_file():
    topo = Topography1DFactory()

    from django.core.files.base import ContentFile
    new_content = ContentFile('\x00')  # some nonsense which cannot be interpreted by module "SurfaceTopography"
    with tempfile.NamedTemporaryFile(mode='wb') as tmp:
        topo.datafile.save(tmp.name, new_content)

    return topo


@pytest.fixture
def user_three_topographies_three_surfaces_three_tags():
    user = UserFactory()

    tag1 = TagModelFactory()
    tag2 = TagModelFactory()
    tag3 = TagModelFactory()

    surface1 = SurfaceFactory(creator=user, tags=[tag1])
    topo1a = Topography1DFactory(surface=surface1)
    topo1b = Topography1DFactory(surface=surface1, tags=[tag2, tag3])

    surface2 = SurfaceFactory(creator=user, tags=[tag2])
    topo2a = Topography1DFactory(surface=surface2, tags=[tag1])

    surface3 = SurfaceFactory(creator=user, tags=[tag3])  # empty

    return user, (topo1a, topo1b, topo2a), (surface1, surface2, surface3), (tag1, tag2, tag3)

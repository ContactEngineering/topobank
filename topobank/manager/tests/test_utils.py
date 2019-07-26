"""
Tests for the interface to topography files
and other things in topobank.manager.utils
"""

import pytest
from pathlib import Path
import io

from ..tests.utils import two_topos
from ..utils import TopographyFile, TopographyFileReadingException,\
    DEFAULT_DATASOURCE_NAME, \
    selection_to_instances, selection_for_select_all, selection_choices
from ..models import Surface

def test_data_sources_txt():

    input_file_path = Path('topobank/manager/fixtures/example4.txt')  # TODO use standardized way to find files

    topofile = TopographyFile(input_file_path)

    assert topofile.data_sources == [DEFAULT_DATASOURCE_NAME]


@pytest.fixture
def mock_topos(mocker):
    mocker.patch('topobank.manager.models.Topography', autospec=True)
    mocker.patch('topobank.manager.models.Surface', autospec=True)

@pytest.fixture
def testuser(django_user_model):
    username = 'testuser'
    user, created = django_user_model.objects.get_or_create(username=username)
    return user

def test_selection_to_instances(testuser, mock_topos):

    from topobank.manager.models import Topography, Surface

    selection = ('topography-1', 'topography-2', 'surface-1', 'surface-3')
    selection_to_instances(selection)

    Topography.objects.filter.assert_called_with(id__in=[1,2])
    Surface.objects.filter.assert_called_with(id__in={1, 3}) # set instead of list

def test_selection_to_instances_with_given_surface(testuser, mock_topos):

    from topobank.manager.models import Topography, Surface

    surface = Surface(name='surface1')

    selection = ('topography-1', 'topography-2', 'surface-1')
    selection_to_instances(selection, surface=surface)

    Topography.objects.filter.assert_called_with(id__in=[1,2], surface=surface)

@pytest.mark.django_db
def test_select_all(two_topos, testuser):
    selection = selection_for_select_all(testuser)
    surfaces = Surface.objects.filter(name__in=["Surface 1", "Surface 2"]).order_by('id')
    assert [ f"surface-{s.id}" for s in surfaces] == sorted(selection)

@pytest.mark.django_db
def test_selection_choices(two_topos, testuser):
    choices = selection_choices(testuser)

    # we expect only one group in choices (1 surface)
    assert len(choices) == 2
    assert choices[0][0] == 'Surface 1 - created by you'
    assert choices[1][0] == 'Surface 2 - created by you'

    # within each group, there should be one choice label,
    # first one this the full surface
    choice_labels = [ x[1] for x in choices[0][1] ]

    assert [ 'Surface 1',
             'Example 3 - ZSensor']  == choice_labels

    choice_labels = [x[1] for x in choices[1][1]]

    assert ['Surface 2',
            'Example 4 - Default'] == choice_labels

def test_topographyfile_loading_invalid_file():

    input_file_path = Path('topobank/manager/views.py')

    with pytest.raises(TopographyFileReadingException):
        TopographyFile(input_file_path)

def test_topographyfile_txt_open_with_fname():
    input_file_path = Path('topobank/manager/fixtures/10x10.txt')
    tf = TopographyFile(input_file_path)
    pyco_topo = tf.topography(0)
    assert pyco_topo.resolution == (10,10)

def test_topographyfile_txt_open_with_text_fobj():
    input_file_path = Path('topobank/manager/fixtures/10x10.txt')

    input_file = open(input_file_path, 'r') # fails with mode 'rb'

    tf = TopographyFile(input_file)
    pyco_topo = tf.topography(0)
    assert pyco_topo.resolution == (10,10)

def test_topographyfile_txt_open_with_text_fobj():
    input_file_path = Path('topobank/manager/fixtures/10x10.txt')

    input_file = open(input_file_path, 'rb')

    tf = TopographyFile(input_file)
    pyco_topo = tf.topography(0)
    assert pyco_topo.resolution == (10,10)


def test_topographyfile_txt_open_with_bytesio():
    input_file_path = Path('topobank/manager/fixtures/10x10.txt')

    input_file = open(input_file_path, 'rb')

    input_data = input_file.read()

    tf = TopographyFile(io.BytesIO(input_data))
    pyco_topo = tf.topography(0)
    assert pyco_topo.resolution == (10,10)


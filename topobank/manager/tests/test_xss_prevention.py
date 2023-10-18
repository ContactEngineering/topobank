import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from .utils import UserFactory, Topography1DFactory, Topography2DFactory, SurfaceFactory
from ..forms import SurfacePublishForm
from ..models import Topography

MALICIOUS_TEXT = "<script>alert('hi')</script>"
BLEACHED_MALICIOUS_TEXT = "&lt;script&gt;alert('hi')&lt;/script&gt;"


@pytest.mark.django_db
def test_surface_description_is_safe():

    user = UserFactory()

    malicious_description = MALICIOUS_TEXT

    form_data = {
        'name': "Hacker's Surface",
        'creator': user.id,
        'description': malicious_description,
        'category': 'exp',
    }
    form_kwargs = {
        'autocomplete_tags': [],
    }

    form = SurfaceForm(data=form_data, **form_kwargs)
    assert form.is_valid(), form.errors

    cleaned = form.clean()
    assert cleaned['description'] == BLEACHED_MALICIOUS_TEXT


@pytest.mark.django_db
def test_topography_description_is_safe_on_update():
    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    topography = Topography1DFactory(surface=surface, size_x=1, size_y=1, tags=[])

    form_initial = {
        'surface': surface.pk,
        'data_source': 0,
        'name': 'nice name',
        'measurement_date': topography.measurement_date,
        'description': 'this is harmless',
        'size_x': 1,
        'size_y': 1,
        'unit': 'nm',
        'height_scale': topography.height_scale,
        'detrend_mode': topography.detrend_mode,
        'tags': [],
        'size_editable': False,
        'unit_editable': False,
        'height_scale_editable': False,
        'instrument_type': Topography.INSTRUMENT_TYPE_UNDEFINED,
        'fill_undefined_data_mode': Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING,
    }
    form_kwargs = {
        'has_size_y': topography.size_y is not None,
        'autocomplete_tags': [],
        'allow_periodic': False,
        'has_undefined_data': None,
    }

    form_data = form_initial.copy()
    form_data['description'] = MALICIOUS_TEXT

    form_files = {
        'datafile': SimpleUploadedFile('test.txt', b'Some content')
    }

    form = TopographyForm(data=form_data, files=form_files, initial=form_initial, **form_kwargs)
    assert form.is_valid(), form.errors

    cleaned = form.clean()
    assert cleaned['description'] == BLEACHED_MALICIOUS_TEXT


@pytest.mark.django_db
def test_topography_description_is_safe_on_creation():
    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    topography = Topography2DFactory(surface=surface, size_x=1, size_y=1, tags=[])

    form_initial = {
        'data_source': 0,
        'name': 'nice name',
        'measurement_date': topography.measurement_date,
        'description': 'this is harmless',
        'tags': [],
    }
    form_kwargs = {
        'surface': surface.id,
        'autocomplete_tags': [],
        'data_source_choices': [ (0,'Default') ],
    }

    form_data = form_initial.copy()
    form_data['description'] = MALICIOUS_TEXT

    form_files = {
        'datafile': SimpleUploadedFile('test.txt', b'Some content')
    }

    form = TopographyMetaDataForm(data=form_data, files=form_files, initial=form_initial, **form_kwargs)
    assert form.is_valid(), form.errors

    cleaned = form.clean()
    assert cleaned['description'] == BLEACHED_MALICIOUS_TEXT


@pytest.mark.django_db
def test_surface_tag_is_safe():

    user = UserFactory()

    form_data = {
        'name': "Hacker's Surface",
        'creator': user.id,
        'description': 'sth',
        'category': 'exp',
        'tags': MALICIOUS_TEXT+","+MALICIOUS_TEXT+"2",
    }
    form_kwargs = {
        'autocomplete_tags': [],
    }

    form = SurfaceForm(data=form_data, **form_kwargs)
    assert form.is_valid(), form.errors

    cleaned = form.clean()
    assert set(cleaned['tags']) == set([BLEACHED_MALICIOUS_TEXT, BLEACHED_MALICIOUS_TEXT + "2"])



@pytest.mark.django_db
def test_topography_tag_is_safe_on_update():
    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    topography = Topography2DFactory(surface=surface, size_x=1, size_y=1, tags=[])

    form_initial = {
        'surface': surface.pk,
        'data_source': 0,
        'name': "nice name",
        'measurement_date': topography.measurement_date,
        'description': 'this is harmless',
        'size_x': 1,
        'size_y': 1,
        'unit': 'nm',
        'height_scale': topography.height_scale,
        'detrend_mode': topography.detrend_mode,
        'tags': [],
        'size_editable': False,
        'unit_editable': False,
        'height_scale_editable': False,
        'instrument_name': '',
        'instrument_type': Topography.INSTRUMENT_TYPE_UNDEFINED,
        'instrument_parameters': '{}',
        'fill_undefined_data_mode': Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING,
    }
    form_kwargs = {
        'has_size_y': topography.size_y is not None,
        'autocomplete_tags': [],
        'allow_periodic': False,
        'has_undefined_data': None,
    }

    form_data = form_initial.copy()
    form_data['tags'] = MALICIOUS_TEXT+","+MALICIOUS_TEXT+"2"

    form_files = {
        'datafile': SimpleUploadedFile('test.txt', b'Some content')
    }

    form = TopographyForm(data=form_data, files=form_files, initial=form_initial, **form_kwargs)
    assert form.is_valid(), form.errors

    cleaned = form.clean()
    assert set(cleaned['tags']) == set([BLEACHED_MALICIOUS_TEXT, BLEACHED_MALICIOUS_TEXT + "2"])


@pytest.mark.django_db
def test_topography_tag_is_safe_on_creation():
    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    topography = Topography2DFactory(surface=surface, size_x=1, size_y=1, tags=[])

    form_initial = {
        'data_source': 0,
        'name': 'nice name',
        'measurement_date': topography.measurement_date,
        'description': 'this is harmless',
        'tags': [],
    }
    form_kwargs = {
        'surface': surface.id,
        'autocomplete_tags': [],
        'data_source_choices': [(0, 'Default')],
    }

    form_data = form_initial.copy()
    form_data['tags'] = MALICIOUS_TEXT + "," + MALICIOUS_TEXT + "2"

    form_files = {
        'datafile': SimpleUploadedFile('test.txt', b'Some content')
    }

    form = TopographyMetaDataForm(data=form_data, files=form_files, initial=form_initial, **form_kwargs)
    assert form.is_valid(), form.errors

    cleaned = form.clean()
    assert set(cleaned['tags']) == set([BLEACHED_MALICIOUS_TEXT, BLEACHED_MALICIOUS_TEXT + "2"])


@pytest.mark.django_db
def test_surface_name_is_safe():
    user = UserFactory()

    form_data = {
        'name': MALICIOUS_TEXT,
        'creator': user.id,
        'description': '',
        'category': 'exp',
    }
    form_kwargs = {
        'autocomplete_tags': [],
    }

    form = SurfaceForm(data=form_data, **form_kwargs)
    assert form.is_valid(), form.errors

    cleaned = form.clean()
    assert cleaned['name'] == BLEACHED_MALICIOUS_TEXT


@pytest.mark.django_db
def test_topography_name_is_safe_on_update():
    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    topography = Topography2DFactory(surface=surface, size_x=1, size_y=1, tags=[])

    form_initial = {
        'surface': surface.pk,
        'data_source': 0,
        'name': "nice name",
        'measurement_date': topography.measurement_date,
        'description': 'this is harmless',
        'size_x': 1,
        'size_y': 1,
        'unit': 'nm',
        'height_scale': topography.height_scale,
        'detrend_mode': topography.detrend_mode,
        'tags': [],
        'size_editable': False,
        'unit_editable': False,
        'height_scale_editable': False,
        'instrument_name': '',
        'instrument_type': Topography.INSTRUMENT_TYPE_UNDEFINED,
        'instrument_parameters': '{}',
        'fill_undefined_data_mode': Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING,
    }
    form_kwargs = {
        'has_size_y': topography.size_y is not None,
        'autocomplete_tags': [],
        'allow_periodic': False,
        'has_undefined_data': None,
    }

    form_data = form_initial.copy()
    form_data['name'] = MALICIOUS_TEXT

    form_files = {
        'datafile': SimpleUploadedFile('test.txt', b'Some content')
    }

    form = TopographyForm(data=form_data, files=form_files, initial=form_initial, **form_kwargs)
    assert form.is_valid(), form.errors

    cleaned = form.clean()
    assert cleaned['name'] == BLEACHED_MALICIOUS_TEXT


@pytest.mark.django_db
def test_topography_name_is_safe_on_creation():
    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    topography = Topography2DFactory(surface=surface, size_x=1, size_y=1, tags=[])

    form_initial = {
        'data_source': 0,
        'name': 'nice name',
        'measurement_date': topography.measurement_date,
        'description': 'this is harmless',
        'tags': [],
    }
    form_kwargs = {
        'surface': surface.id,
        'autocomplete_tags': [],
        'data_source_choices': [(0, 'Default')],
    }
    form_data = form_initial.copy()
    form_data['name'] = MALICIOUS_TEXT

    form_files = {
        'datafile': SimpleUploadedFile('test.txt', b'Some content')
    }

    form = TopographyMetaDataForm(data=form_data, files=form_files, initial=form_initial, **form_kwargs)
    assert form.is_valid(), form.errors

    cleaned = form.clean()
    assert cleaned['name'] == BLEACHED_MALICIOUS_TEXT


def test_author_is_safe():
    form_data = {
        'authors_json': [{'first_name': 'Draco', 'last_name': MALICIOUS_TEXT, 'orcid_id': '', 'affiliations': []}],
        'license': 'cc0-1.0',
        'agreed': True,
        'copyright_hold': True,
    }
    form = SurfacePublishForm(data=form_data)
    assert form.is_valid()

    cleaned = form.clean()
    assert cleaned['authors_json'] == [{'first_name': 'Draco',
                                        'last_name': BLEACHED_MALICIOUS_TEXT,
                                        'orcid_id': '', 'affiliations': []}]


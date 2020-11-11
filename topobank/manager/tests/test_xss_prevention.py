import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from .utils import UserFactory, TopographyFactory, SurfaceFactory
from ..forms import SurfaceForm, TopographyForm, SurfacePublishForm


MALICIOUS_TEXT = "<script>alert('hi')</script>"
ESCAPED_MALICIOUS_TEXT = "&lt;script&gt;alert(&#39;hi&#39;)&lt;/script&gt;"

@pytest.mark.django_db
def test_surface_description_is_safe():

    user = UserFactory()
    surface = SurfaceFactory(creator=user, name="Hacker's Surface")

    malicious_description = MALICIOUS_TEXT

    form_data={
        'name': surface.name,
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
    assert cleaned['description'] == ESCAPED_MALICIOUS_TEXT


@pytest.mark.django_db
def test_topography_description_is_safe():
    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    topography = TopographyFactory(surface=surface, size_x=1, size_y=1, tags=[])

    malicious_description = MALICIOUS_TEXT

    form_data = {
        'surface': surface.pk,
        'data_source': 0,
        'name': 'nice name',
        'measurement_date': topography.measurement_date,
        'description': malicious_description,
        'size_x': 1,
        'size_y': 1,
        'unit': 'nm',
        'height_scale': topography.height_scale,
        'detrend_mode': topography.detrend_mode,
        'tags': [],
        'size_editable': False,
        'unit_editable': False,
        'height_scale_editable': False,
    }
    form_kwargs = {
        'has_size_y': topography.size_y is not None,
        'autocomplete_tags': [],
        'allow_periodic': False,
    }

    form_files = {
        'datafile': SimpleUploadedFile('test.txt', b'Some content')
    }

    form = TopographyForm(data=form_data, files=form_files, initial=form_data, **form_kwargs)
    assert form.is_valid(), form.errors

    cleaned = form.clean()
    assert cleaned['description'] == ESCAPED_MALICIOUS_TEXT


def test_author_is_safe():
    malicious_author = MALICIOUS_TEXT

    form_data = {
        'author_0': malicious_author,
        'num_author_fields': 1,
        'license': 'cc0-1.0',
        'agreed': True,
        'copyright_hold': True,
    }
    form = SurfacePublishForm(data=form_data, num_author_fields=1)
    assert form.is_valid()

    cleaned = form.clean()
    assert cleaned['authors'] == ESCAPED_MALICIOUS_TEXT


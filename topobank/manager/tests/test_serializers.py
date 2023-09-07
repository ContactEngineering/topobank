import pytest
from django.shortcuts import reverse

from ..serializers import SurfaceSerializer
from ..utils import subjects_to_base64
from .utils import SurfaceFactory, Topography1DFactory, UserFactory, ordereddicts_to_dicts


@pytest.mark.django_db
def test_surface_serializer(rf):
    user = UserFactory()
    surface1 = SurfaceFactory(name='mysurface', creator=user)
    topo1a = Topography1DFactory(surface=surface1)
    topo1b = Topography1DFactory(surface=surface1)
    surface2 = SurfaceFactory(name='mysurface', creator=user)

    surface1.tags = ['bike', 'train/tgv']
    surface1.save()

    request = rf.get(reverse('home'))  # any request
    request.user = user

    context = dict(
        request=request,
        selected_instances=([topo1a], [surface2], []),  # no tags selected here (3rd list is empty)
    )

    surfser = SurfaceSerializer(context=context)

    result = ordereddicts_to_dicts([surfser.to_representation(surface1)], sorted_by='url')

    #
    # prepare some abbreviations
    #
    user_url = request.build_absolute_uri(f'/users/api/user/{user.id}/')
    assert result[0] == {
        'creator': user_url,
        'category': None,
        'description': '',
        'name': surface1.name,
        'url': f'http://testserver/manager/api/surface/{surface1.id}/',
        'topography_set': [{'bandwidth_lower': None,
                            'bandwidth_upper': None,
                            'creator': user_url,
                            'datafile_format': None,
                            'description': '',
                            'detrend_mode': 'center',
                            'fill_undefined_data_mode': 'do-not-fill',
                            'has_undefined_data': None,
                            'height_scale': 1.0,
                            'height_scale_editable': True,
                            'instrument_name': '',
                            'instrument_parameters': {},
                            'instrument_type': 'undefined',
                            'is_periodic': False,
                            'measurement_date': '2019-01-01',
                            'name': f'topography-00000',
                            'resolution_x': None,
                            'resolution_y': None,
                            'short_reliability_cutoff': None,
                            'size_editable': False,
                            'size_x': 512.0,
                            'size_y': None,
                            'surface': f'http://testserver/manager/api/surface/{surface1.id}/',
                            'unit': 'nm',
                            'unit_editable': False,
                            'url': f'http://testserver/manager/api/topography/{topo1a.id}/'},
                           {'bandwidth_lower': None,
                            'bandwidth_upper': None,
                            'creator': user_url,
                            'datafile_format': None,
                            'description': '',
                            'detrend_mode': 'center',
                            'fill_undefined_data_mode': 'do-not-fill',
                            'has_undefined_data': None,
                            'height_scale': 1.0,
                            'height_scale_editable': True,
                            'instrument_name': '',
                            'instrument_parameters': {},
                            'instrument_type': 'undefined',
                            'is_periodic': False,
                            'measurement_date': '2019-01-02',
                            'name': f'topography-00001',
                            'resolution_x': None,
                            'resolution_y': None,
                            'short_reliability_cutoff': None,
                            'size_editable': False,
                            'size_x': 512.0,
                            'size_y': None,
                            'surface': f'http://testserver/manager/api/surface/{surface1.id}/',
                            'unit': 'nm',
                            'unit_editable': False,
                            'url': f'http://testserver/manager/api/topography/{topo1b.id}/'}]
    }

import pytest
from django.shortcuts import reverse

from ..serializers import TopographySerializer, SurfaceSerializer
from .utils import SurfaceFactory, TopographyFactory, UserFactory, ordereddicts_to_dicts

@pytest.mark.django_db
def test_surface_serializer(rf):
    user = UserFactory()
    surface1 = SurfaceFactory(name='mysurface', creator=user)
    topo1a = TopographyFactory(surface=surface1)
    topo1b = TopographyFactory(surface=surface1)
    surface2 = SurfaceFactory(name='mysurface', creator=user)

    surface1.tags = ['bike', 'train/tgv']
    surface1.save()

    request = rf.get(reverse('home')) # any request
    request.user = user

    context = dict(
        request = request,
        selected_instances = ([topo1a], [surface2]),
    )

    surfser = SurfaceSerializer(context=context)

    result = ordereddicts_to_dicts([surfser.to_representation(surface1)])

    #
    # prepare some abbreviations
    #
    user_url = request.build_absolute_uri(user.get_absolute_url())
    surface1_prefix = f"/manager/surface/{surface1.pk}/"
    topo1a_prefix = f"/manager/topography/{topo1a.pk}/"
    topo1b_prefix = f"/manager/topography/{topo1b.pk}/"
    surface2_prefix = f"/manager/surface/{surface2.pk}/"

    assert result[0] == {

        'category': None,
        'children': [
            {'creator': user_url,
             'description': '',
             'folder': False,
             'key': f'topography-{topo1a.pk}',
             'surface_key': f'surface-{surface1.pk}',
             'name': topo1a.name,
             'pk': topo1a.pk,
             'selected': True,
             'tags': [],
             'title': topo1a.name,
             'type': 'topography',
             'urls': {'delete': topo1a_prefix + 'delete/',
                      'detail': topo1a_prefix,
                      'select': topo1a_prefix + 'select/',
                      'show_analyses': topo1a_prefix + 'show-analyses/',
                      'unselect': topo1a_prefix + 'unselect/',
                      'update': topo1a_prefix + 'update/'}},
            {'creator': user_url,
             'description': '',
             'folder': False,
             'key': f'topography-{topo1b.pk}',
             'surface_key': f'surface-{surface1.pk}',
             'name': topo1b.name,
             'pk': topo1b.pk,
             'selected': False,
             'tags': [],
             'title': topo1b.name,
             'type': 'topography',
             'urls': {'delete': topo1b_prefix + 'delete/',
                      'detail': topo1b_prefix,
                      'select': topo1b_prefix + 'select/',
                      'show_analyses': topo1b_prefix + 'show-analyses/',
                      'unselect': topo1b_prefix + 'unselect/',
                      'update': topo1b_prefix + 'update/'}},

        ],
        'creator': user_url,
        'description': '',
        'folder': True,
        'key': f'surface-{surface1.pk}',
        'name': surface1.name,
        'pk': surface1.pk,
        'selected': False,
        'sharing_status': 'own',
        'tags': ['bike', 'train/tgv'],
        'title': surface1.name,
        'type': 'surface',
        'urls': {'add_topography': surface1_prefix + 'new-topography/',
                 'delete': surface1_prefix + 'delete/',
                 'detail': surface1_prefix,
                 'download': surface1_prefix + 'download/',
                 'select': surface1_prefix + 'select/',
                 'share': surface1_prefix + 'share/',
                 'show_analyses': surface1_prefix + 'show-analyses/',
                 'unselect': surface1_prefix + 'unselect/',
                 'update': surface1_prefix + 'update/'}

    }

"""
Tests for the interface to topography files
and other things in topobank.manager.utils
"""

import pytest

from ..tests.utils import two_topos
from ..utils import selection_to_instances, instances_to_selection, tags_for_user
from ..models import Surface, Topography, TagModel


@pytest.fixture
def mock_topos(mocker):
    mocker.patch('topobank.manager.models.Topography', autospec=True)
    mocker.patch('topobank.manager.models.Surface', autospec=True)
    mocker.patch('topobank.manager.models.TagModel', autospec=True)

@pytest.fixture
def testuser(django_user_model):
    username = 'testuser'
    user, created = django_user_model.objects.get_or_create(username=username)
    return user

def test_selection_to_instances(testuser, mock_topos):

    from topobank.manager.models import Topography, Surface, TagModel

    selection = ('topography-1', 'topography-2', 'surface-1', 'surface-3', 'tag-1', 'tag-2', 'tag-4')
    selection_to_instances(selection)

    Topography.objects.filter.assert_called_with(id__in=[1,2])
    Surface.objects.filter.assert_called_with(id__in={1, 3})  # set instead of list
    TagModel.objects.filter.assert_called_with(id__in={1, 2, 4})  # set instead of list

def test_selection_to_instances_with_given_surface(testuser, mock_topos):

    from topobank.manager.models import Topography, Surface

    surface = Surface(name='surface1')

    selection = ('topography-1', 'topography-2', 'surface-1')
    selection_to_instances(selection, surface=surface)

    Topography.objects.filter.assert_called_with(id__in=[1,2], surface=surface)


@pytest.mark.django_db
def test_instances_to_selection(two_topos):

    topo1 = Topography.objects.get(name="Example 3 - ZSensor")
    topo2 = Topography.objects.get(name="Example 4 - Default")

    surface1 = Surface.objects.get(name="Surface 1")
    surface2 = Surface.objects.get(name="Surface 2")

    assert topo1.surface != topo2.surface

    s = instances_to_selection(topographies=[topo1, topo2])

    assert s == [f'topography-{topo1.id}', f'topography-{topo2.id}']

    #
    # Giving an extra surface here should make no difference
    #
    s = instances_to_selection(topographies=[topo1, topo2])
    assert s == [f'topography-{topo1.id}', f'topography-{topo2.id}']

    #
    # Should be summarized to one surface if all topographies are given?
    #
    #topo2.surface = topo1.surface
    #topo2.save()
    #s = instances_to_selection([topo1, topo2])
    #assert s == [f'surface-{topo1.surface.id}']

    #
    # It should be possible to give surfaces
    #
    s = instances_to_selection(surfaces=[surface1, surface2])
    assert s == [f'surface-{surface1.id}', f'surface-{surface2.id}']

@pytest.mark.django_db
def test_tags_for_user(two_topos):

    topo1 = Topography.objects.get(name="Example 3 - ZSensor")
    topo1.tags = ['rough', 'projects/a']
    topo1.save()

    from topobank.manager.models import TagModel
    print("Tags of topo1:", topo1.tags)
    print(TagModel.objects.all())

    topo2 = Topography.objects.get(name="Example 4 - Default")
    topo2.tags = ['interesting']
    topo2.save()

    surface1 = Surface.objects.get(name="Surface 1")
    surface1.tags = ['projects/C', 'rare']
    surface1.save()

    surface2 = Surface.objects.get(name="Surface 2")
    surface2.tags = ['projects/B', 'a long tag with spaces']
    surface2.save()

    user = surface1.creator

    assert surface2.creator == user

    tags = tags_for_user(user)

    assert set( t.name for t in tags) == {'a long tag with spaces', 'interesting', 'rare', 'rough',
                                          'projects/a', 'projects/b', 'projects/c', 'projects'}



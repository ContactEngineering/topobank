import pytest
import datetime

from django.shortcuts import reverse
from guardian.shortcuts import get_perms

from .utils import SurfaceFactory, UserFactory, TopographyFactory, TagModelFactory
from topobank.utils import assert_in_content, assert_redirects, assert_not_in_content


@pytest.mark.django_db
def test_publication_version():
    surface = SurfaceFactory()
    publication_v1 = surface.publish('cc0')

    assert publication_v1.version == 1

    surface.name = "new name"
    publication_v2 = surface.publish('cc0')
    assert publication_v2.version == 2

    assert publication_v1.original_surface == publication_v2.original_surface
    assert publication_v1.surface != publication_v2.surface


@pytest.mark.django_db
def test_publication_fields():
    surface = SurfaceFactory()
    publication = surface.publish('cc0')

    assert publication.license == 'cc0'
    assert publication.original_surface == surface
    assert publication.surface != publication.original_surface
    assert publication.publisher == surface.creator
    assert publication.version == 1


@pytest.mark.django_db
def test_published_field():
    surface = SurfaceFactory()
    assert not surface.is_published
    publication = surface.publish('cc0')
    assert not publication.original_surface.is_published
    assert publication.surface.is_published


@pytest.mark.django_db
def test_permissions_for_published():
    surface = SurfaceFactory()
    user1 = surface.creator
    user2 = UserFactory()

    # before publishing, user1 is allowed everything,
    # user2 nothing
    assert set(get_perms(user1, surface)) == set(['view_surface', 'delete_surface', 'change_surface',
                                                  'share_surface', 'publish_surface'])
    assert get_perms(user2, surface) == []

    # for the published surface, both users are only allowed viewing
    publication = surface.publish('cc0')

    assert get_perms(user1, publication.surface) == ['view_surface']
    assert get_perms(user2, publication.surface) == ['view_surface']

    # the permissions for the original surface has not been changed


@pytest.mark.django_db
def test_surface_deepcopy():

    tag1 = TagModelFactory()
    tag2 = TagModelFactory()

    datea = datetime.date(2020, 7, 1)
    dateb = datetime.date(2020, 7, 2)

    surface1 = SurfaceFactory(description="test", tags=[tag1])
    topo1a = TopographyFactory(surface=surface1, name='a',
                               measurement_date=datea, tags=[tag2],
                               description="This is a)")
    topo1b = TopographyFactory(surface=surface1, name='b',
                               measurement_date=dateb, tags=[tag1, tag2],
                               description="This is b)")

    surface2 = surface1.deepcopy()

    assert surface1.id != surface2.id  # really different objects

    assert surface1.name == surface2.name
    assert surface1.category == surface2.category
    assert surface1.creator == surface2.creator
    assert surface1.description == surface2.description
    assert surface1.tags == surface2.tags

    topo2a = surface2.topography_set.get(name='a')
    topo2b = surface2.topography_set.get(name='b')

    for t1, t2 in ((topo1a, topo2a), (topo1b, topo2b)):
        assert t1.id != t2.id  # really different objects
        assert t1.measurement_date == t2.measurement_date
        assert t1.datafile != t2.datafile

        assert t1.tags == t2.tags

        assert t1.size_x == t2.size_x
        assert t1.size_y == t2.size_y
        assert t1.description == t2.description

        assert t1.datafile.name != t2.datafile.name  # must be unique

        # file contents should be the same
        assert t1.datafile.open(mode='rb').read() == t2.datafile.open(mode='rb').read()
        assert t1.data_source == t2.data_source
        assert t1.datafile_format == t2.datafile_format


@pytest.mark.django_db
def test_switch_versions_on_properties_tab(client):

    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    topo1 = TopographyFactory(surface=surface)
    topo2 = TopographyFactory(surface=surface)

    #
    # First: The surface is not published yet
    #
    client.force_login(user)

    response = client.get(reverse('manager:surface-detail', kwargs=dict(pk=surface.pk)))

    assert response.status_code == 200
    assert_not_in_content(response, 'Version 1')
    assert_not_in_content(response, 'Version 2')

    #
    # Now publish the first time
    #
    publication = surface.publish('cc0')
    assert publication.version == 1
    assert publication.license == 'cc0'
    assert publication.original_surface == surface
    pub_date_1 = publication.datetime.date()

    response = client.get(reverse('manager:surface-detail', kwargs=dict(pk=surface.pk)))

    assert response.status_code == 200
    assert_in_content(response, 'Version 1 ({})'.format(pub_date_1))
    assert_not_in_content(response, 'Version 2')

    #
    # Publish again
    #
    publication = surface.publish('cc0')
    assert publication.version == 2
    assert publication.original_surface == surface
    pub_date_2 = publication.datetime.date()

    response = client.get(reverse('manager:surface-detail', kwargs=dict(pk=surface.pk)))

    assert response.status_code == 200
    assert_in_content(response, 'Version 1 ({})'.format(pub_date_1))
    assert_in_content(response, 'Version 2 ({})'.format(pub_date_2))











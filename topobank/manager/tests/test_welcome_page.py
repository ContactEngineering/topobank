import pytest
from django.shortcuts import reverse

from topobank.manager.tests.utils import SurfaceFactory, TopographyFactory, UserFactory
from topobank.analysis.tests.utils import AnalysisFactory

from topobank.utils import assert_in_content


@pytest.mark.django_db
@pytest.fixture
def test_instances():

    users = [
        UserFactory(username='user1'),
        UserFactory(username='user2')
    ]

    surfaces = [
        SurfaceFactory(creator=users[0]),
        SurfaceFactory(creator=users[0]),
    ]

    topographies = [
        TopographyFactory(surface=surfaces[0])
    ]

    AnalysisFactory(topography=topographies[0])

    return users, surfaces, topographies


@pytest.mark.django_db
@pytest.mark.parametrize('with_publication', [False, True])
def test_welcome_page_statistics(client, test_instances, with_publication):

    (user_1, user_2), (surface_1, surface_2), (topography_1,) = test_instances
    surface_2.share(user_2)

    if with_publication:
        surface_1.publish('cc0-1.0', 'Issac Newton')

    #
    # Test statistics if user is not yet authenticated
    #
    response = client.get(reverse('home'))

    assert_in_content(response, '<div class="welcome-page-statistics">2</div> registered users')
    assert_in_content(response, '<div class="welcome-page-statistics">2</div> surfaces in the database')
    assert_in_content(response, '<div class="welcome-page-statistics">1</div> individual topographies')
    assert_in_content(response, '<div class="welcome-page-statistics">1</div> computed analyses')

    #
    # Test statistics if user_1 is authenticated
    #
    client.force_login(user_1)
    response = client.get(reverse('home'))

    assert_in_content(response, '<div class="welcome-page-statistics">2</div> surfaces in the database')
    assert_in_content(response, '<div class="welcome-page-statistics">1</div> individual topographies')
    assert_in_content(response, '<div class="welcome-page-statistics">1</div> computed analyses')
    assert_in_content(response, '<div class="welcome-page-statistics">0</div> surfaces of other users')

    client.logout()

    #
    # Test statistics if user_2 is authenticated
    #
    client.force_login(user_2)
    response = client.get(reverse('home'))

    assert_in_content(response, '<div class="welcome-page-statistics">0</div> surfaces in the database')
    assert_in_content(response, '<div class="welcome-page-statistics">0</div> individual topographies')
    assert_in_content(response, '<div class="welcome-page-statistics">0</div> computed analyses')
    if with_publication:
        num_access = 2
    else:
        num_access = 1
    assert_in_content(response, f'<div class="welcome-page-statistics">{num_access}</div> surfaces of other users')

    client.logout()



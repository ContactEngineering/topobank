import pytest
from django.shortcuts import reverse

from topobank.utils import assert_in_content

from topobank.analysis.tests.utils import TopographyAnalysisFactory
from topobank.manager.tests.utils import SurfaceFactory, Topography1DFactory, UserFactory


@pytest.mark.django_db
@pytest.fixture
def test_instances(test_analysis_function):

    users = [
        UserFactory(username='user1'),
        UserFactory(username='user2')
    ]

    surfaces = [
        SurfaceFactory(creator=users[0]),
        SurfaceFactory(creator=users[0]),
    ]

    topographies = [
        Topography1DFactory(surface=surfaces[0])
    ]

    TopographyAnalysisFactory(function=test_analysis_function, subject_topography=topographies[0])

    return users, surfaces, topographies


@pytest.mark.django_db
def test_welcome_page_statistics(client, test_instances, handle_usage_statistics):

    (user_1, user_2), (surface_1, surface_2), (topography_1,) = test_instances
    surface_2.share(user_2)

    #
    # Test statistics if user is not yet authenticated
    #
    response = client.get(reverse('home'))

    assert_in_content(response, '<div class="welcome-page-statistics">2</div> registered users')
    assert_in_content(response, '<div class="welcome-page-statistics">2</div> digital surface twins')
    assert_in_content(response, '<div class="welcome-page-statistics">1</div> individual measurements')
    assert_in_content(response, '<div class="welcome-page-statistics">1</div> computed analyses')

    #
    # Test statistics if user_1 is authenticated
    #
    client.force_login(user_1)
    response = client.get(reverse('home'))

    assert_in_content(response, '<div class="welcome-page-statistics">2</div> digital surface twins')
    assert_in_content(response, '<div class="welcome-page-statistics">1</div> individual measurements')
    assert_in_content(response, '<div class="welcome-page-statistics">1</div> computed analyses')
    assert_in_content(response, '<div class="welcome-page-statistics">0</div> digital twins of other users')

    client.logout()

    #
    # Test statistics if user_2 is authenticated
    #
    client.force_login(user_2)
    response = client.get(reverse('home'))

    assert_in_content(response, '<div class="welcome-page-statistics">0</div> digital surface twins')
    assert_in_content(response, '<div class="welcome-page-statistics">0</div> individual measurements')
    assert_in_content(response, '<div class="welcome-page-statistics">0</div> computed analyses')
    assert_in_content(response, f'<div class="welcome-page-statistics">1</div> digital twins of other users')

    client.logout()



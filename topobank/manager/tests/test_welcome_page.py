
from django.shortcuts import reverse

from topobank.manager.tests.utils import SurfaceFactory, TopographyFactory

from topobank.utils import assert_in_content

def test_welcome_page_statistics(client, django_user_model):

    password = "secret"

    #
    # create some database objects
    #
    user_1 = django_user_model.objects.create_user(username='user1', password=password)
    user_2 = django_user_model.objects.create_user(username='user2', password=password)

    surface_1 = SurfaceFactory(user=user_1)
    surface_2 = SurfaceFactory(user=user_1)
    topography_1 = TopographyFactory(surface=surface_1)

    #
    # Test statistics if user is not yet authenticated
    #
    response = client.get(reverse('home'))

    assert_in_content(response, '<div class="welcome-page-statistics">2</div> registered users')
    assert_in_content(response, '<div class="welcome-page-statistics">2</div> surfaces in database')
    assert_in_content(response, '<div class="welcome-page-statistics">1</div> individual topographies')

    #
    # Test statistics if first user is authenticated
    #
    assert client.login(username=user_1.username, password=password)
    response = client.get(reverse('home'))

    assert_in_content(response, "Your last login was on")
    assert_in_content(response, '<div class="welcome-page-statistics">2</div> surfaces in database')
    assert_in_content(response, '<div class="welcome-page-statistics">1</div> individual topographies')

    client.logout()

    #
    # Test statistics if second user is authenticated
    #
    assert client.login(username=user_2.username, password=password)
    response = client.get(reverse('home'))

    assert_in_content(response, "Your last login was on")
    assert_in_content(response, '<div class="welcome-page-statistics">0</div> surfaces in database')
    assert_in_content(response, '<div class="welcome-page-statistics">0</div> individual topographies')

    client.logout()

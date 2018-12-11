"""
Tests related to user support.
"""
from django.urls import reverse
import pytest

from topobank.manager.models import Surface

@pytest.mark.db_django
def test_initial_surface(live_server, client, django_user_model):

    import topobank.users.signals # in order to have signals activated

    email = "newuser@example.org"
    password = "test$1234"
    name = 'New User'

    response = client.post(reverse('account_signup'),
                {
                    'email': email,
                    'password1': password,
                    'password2': password,
                    'name': name,
                })

    assert 'form' not in response.context, "Errors in form: {}".format(response.context['form'].errors)

    assert response.status_code == 302 # redirect

    user = django_user_model.objects.get(email=email)

    assert client.login(username=email, password=password)

    #
    # There should be an example surface now with three topographies
    #
    surface = Surface.objects.get(user=user, name="Example Surface")

    topos = surface.topography_set.all()

    assert len(topos) == 3

    assert sorted([ t.name for t in topos]) == [ "50000x50000_random.txt",
                                                 "5000x5000_random.txt",
                                                 "500x500_random.txt" ]








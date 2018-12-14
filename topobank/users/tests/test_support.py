"""
Tests related to user support.
"""
from django.urls import reverse
import pytest

from topobank.manager.models import Surface
from topobank.analysis.models import AnalysisFunction, Analysis
import topobank.analysis.functions

@pytest.mark.db_django
def test_initial_surface(live_server, client, django_user_model):

    import topobank.users.signals # in order to have signals activated

    #
    # Make sure, we have automated analysis functions
    #
    topobank.analysis.functions.register_all()

    #
    # signup for an account
    #
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
    # After login, there should be an example surface now with three topographies
    #
    surface = Surface.objects.get(user=user, name="Example Surface")

    topos = surface.topography_set.all()

    assert len(topos) == 3

    assert sorted([ t.name for t in topos]) == [ "50000x50000_random.txt",
                                                 "5000x5000_random.txt",
                                                 "500x500_random.txt" ]

    #
    # For all these topographies, all analyses for all automated analysis functions
    # should have been triggered
    #
    for af in AnalysisFunction.objects.filter(automatic=True):
        analyses = Analysis.objects.filter(topography__surface_id__in=[t.id for t in topos], function=af)
        assert analyses.count() == len(topos)








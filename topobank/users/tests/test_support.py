"""
Tests related to user support.
"""
from django.urls import reverse
from django.core.management import call_command
import pytest
from notifications.models import Notification

from topobank.manager.models import Surface
from topobank.analysis.models import AnalysisFunction, Analysis


@pytest.mark.django_db
def test_initial_surface(client, django_user_model, handle_usage_statistics, mocker):

    import django.db.transaction
    mocker.patch.object(django.db.transaction, 'on_commit', lambda t: t())
    mocker.patch('topobank.taskapp.tasks.perform_analysis.delay')  # we don't want to calculate anything
    # we just skip the waiting for a commit, not needed for this test: Just execute the given function
    # -> like this we need no transaction=True for this test which makes Travis just wait and the tests fail

    call_command("register_analysis_functions")

    # we read from static files, they should be up-to-date
    call_command('collectstatic', '--noinput')

    #
    # signup for an account, this triggers signal to create example surface
    #
    email = "testuser@example.org"
    password = "test$1234"
    name = 'New User'

    response = client.post(reverse('account_signup'), {
                   'email': email,
                   'password1': password,
                   'password2': password,
                   'name': name,
    })
    assert 'form' not in response.context, "Errors in form: {}".format(response.context['form'].errors)

    assert response.status_code == 302  # redirect

    user = django_user_model.objects.get(name=name)

    # user is already authenticated
    assert user.is_authenticated

    #
    # After login, there should be an example surface now with three topographies
    #
    surface = Surface.objects.get(creator=user, name="Example Surface")

    assert surface.category == 'sim'

    topos = surface.topography_set.all()

    assert len(topos) == 3

    assert sorted([t.name for t in topos]) == ["50000x50000_random.txt",
                                               "5000x5000_random.txt",
                                               "500x500_random.txt"]

    #
    # All these topographies should have the same size as in the database
    # and the height scale should be editable
    #
    for topo in topos:
        assert topo.size_x == topo.size_y  # so far all examples are like this, want to ensure here that size_y is set
        st_topo = topo.topography()
        assert st_topo.info['unit'] == 'µm'
        assert st_topo.physical_sizes == (topo.size_x, topo.size_y)

        assert topo.height_scale_editable

    #
    # For all these topographies, all analyses for all analysis functions
    # should have been triggered
    #
    for af in AnalysisFunction.objects.all():
        analyses = Analysis.objects.filter(topography__surface_id=surface.id, function=af)
        assert analyses.count() == len(topos)

    #
    # There should be a notification of the user
    #
    assert Notification.objects.filter(unread=True, recipient=user, verb='create',
                                       description__contains="An example surface has been created for you").count() == 1





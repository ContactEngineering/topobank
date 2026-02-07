"""
Test for results view.
"""

import datetime

import pytest
from django.urls import reverse

from topobank.analysis.models import Workflow, WorkflowResult
from topobank.manager.models import Topography
from topobank.manager.utils import dict_to_base64, subjects_to_base64
from topobank.testing.factories import (
    PermissionSetFactory,
    SurfaceAnalysisFactory,
    SurfaceFactory,
    Topography1DFactory,
    TopographyAnalysisFactory,
    UserFactory,
)


@pytest.mark.django_db
def test_analysis_times(
    api_client, two_topos, test_analysis_function, handle_usage_statistics
):
    topo = Topography.objects.first()

    # we make sure to have to right user who has access
    user = topo.surface.created_by
    api_client.force_login(user)

    TopographyAnalysisFactory.create(
        user=user,
        subject_topography=topo,
        function=test_analysis_function,
        task_state=WorkflowResult.SUCCESS,
        task_start_time=datetime.datetime(2018, 1, 1, 12),
        task_end_time=datetime.datetime(
            2018, 1, 1, 13, 1, 1
        ),  # duration: 1 hour, 1 minute, 1 sec
    )

    response = api_client.get(
        reverse(
            "analysis:card-series",
            kwargs=dict(workflow=test_analysis_function.name),
        )
        + "?subjects="
        + subjects_to_base64([topo])
    )

    assert response.status_code == 200

    analyses = response.data["analyses"]
    assert len(analyses) == 1
    assert analyses[0]["task_start_time"] == "2018-01-01T12:00:00+01:00"
    assert analyses[0]["task_duration"] == "01:01:01"


@pytest.mark.django_db
def test_show_only_last_analysis(
    api_client, two_topos, test_analysis_function, handle_usage_statistics
):
    topo1 = Topography.objects.first()
    topo2 = Topography.objects.last()

    user = topo1.surface.created_by
    api_client.force_login(user)

    result = {
        "name": "test function",
        "xlabel": "x",
        "ylabel": "y",
        "xunit": "1",
        "yunit": "1",
        "series": [],
    }

    #
    # Topography 1
    #
    TopographyAnalysisFactory.create(
        user=user,
        subject_topography=topo1,
        function=test_analysis_function,
        task_state=WorkflowResult.SUCCESS,
        kwargs=test_analysis_function.get_default_kwargs(),
        task_start_time=datetime.datetime(2018, 1, 1, 12),
        task_end_time=datetime.datetime(2018, 1, 1, 13, 1, 1),
        result=result,
    )
    # save a second only, which has a later start time
    TopographyAnalysisFactory.create(
        user=user,
        subject_topography=topo1,
        function=test_analysis_function,
        task_state=WorkflowResult.SUCCESS,
        kwargs=test_analysis_function.get_default_kwargs(),
        task_start_time=datetime.datetime(2018, 1, 2, 12),
        task_end_time=datetime.datetime(2018, 1, 2, 13, 1, 1),
        result=result,
    )

    #
    # Topography 2
    #
    TopographyAnalysisFactory.create(
        user=user,
        subject_topography=topo2,
        function=test_analysis_function,
        task_state=WorkflowResult.SUCCESS,
        kwargs=test_analysis_function.get_default_kwargs(),
        task_start_time=datetime.datetime(2018, 1, 3, 12),
        task_end_time=datetime.datetime(2018, 1, 3, 13, 1, 1),
        result=result,
    )

    # save a second only, which has a later start time
    TopographyAnalysisFactory.create(
        user=user,
        subject_topography=topo2,
        function=test_analysis_function,
        task_state=WorkflowResult.SUCCESS,
        kwargs=test_analysis_function.get_default_kwargs(),
        task_start_time=datetime.datetime(2018, 1, 4, 12),
        task_end_time=datetime.datetime(2018, 1, 4, 13, 1, 1),
        result=result,
    )

    #
    # Check response, for both topographies only the
    # latest results should be shown
    #
    response = api_client.get(
        reverse(
            "analysis:card-series",
            kwargs=dict(workflow=test_analysis_function.name),
        )
        + "?subjects="
        + subjects_to_base64([topo1, topo2])
    )

    assert response.status_code == 200

    analyses = response.data["analyses"]
    assert len(analyses) == 2
    assert analyses[0]["task_start_time"] == "2018-01-02T12:00:00+01:00"
    assert analyses[1]["task_start_time"] == "2018-01-04T12:00:00+01:00"


@pytest.mark.django_db
def test_warnings_for_different_arguments(api_client, handle_usage_statistics):
    user = UserFactory()
    surf1 = SurfaceFactory(created_by=user)
    surf2 = SurfaceFactory(created_by=user)
    topo1a = Topography1DFactory(surface=surf1)
    topo1b = Topography1DFactory(surface=surf1)
    topo2a = Topography1DFactory(surface=surf2)

    func = Workflow.objects.get(name="topobank.testing.test")

    #
    # Generate analyses for topographies with differing arguments
    #
    kwargs_1a = dict(a=1, b="abc")
    kwargs_1b = dict(a=1, b="def")  # differing from kwargs_1a!
    TopographyAnalysisFactory(
        subject_topography=topo1a, function=func, kwargs=kwargs_1a
    )
    TopographyAnalysisFactory(
        subject_topography=topo1b, function=func, kwargs=kwargs_1b
    )
    TopographyAnalysisFactory(
        subject_topography=topo2a, function=func
    )  # default arguments

    #
    # Generate analyses for surfaces with differing arguments
    #
    kwargs_1 = dict(a=2, b="abc")
    kwargs_2 = dict(a=2, b="def")  # differing from kwargs_1a!
    SurfaceAnalysisFactory(subject_surface=surf1, function=func, kwargs=kwargs_1)
    SurfaceAnalysisFactory(subject_surface=surf2, function=func, kwargs=kwargs_2)

    api_client.force_login(user)

    #
    # request card, there should be warnings, one for topographies and one for surfaces
    #
    response = api_client.get(
        reverse("analysis:card-series", kwargs=dict(workflow=func.name))
        + "?subjects="
        + subjects_to_base64([topo1a, topo1b, topo2a, surf1, surf2])
    )

    assert response.status_code == 200
    assert response.data["has_nonunique_kwargs"]


@pytest.mark.skip(
    reason="V1 API uses a get request to get and create analyses, "
    "sharing surface does not give permission to that surface's analyses.")
@pytest.mark.django_db
def test_shared_topography_triggers_no_new_analysis(
    api_client, handle_usage_statistics
):
    password = "abcd$1234"

    #
    # create database objects
    #
    user1 = UserFactory(password=password)
    user2 = UserFactory(password=password)

    surface1 = SurfaceFactory(created_by=user1)
    surface2 = SurfaceFactory(created_by=user2)

    # create topographies + functions + analyses
    func1 = Workflow.objects.get(name="topobank.testing.test")
    # func2 = WorkflowFactory()

    # Two topographies for surface1
    topo1a = Topography1DFactory(surface=surface1, name="topo1a")
    topo1b = Topography1DFactory(surface=surface1, name="topo1b")

    # One topography for surface2
    topo2a = Topography1DFactory(surface=surface2, name="topo2a")

    # analyses, differentiate by start time
    TopographyAnalysisFactory(
        subject_topography=topo1a,
        function=func1,
        task_start_time=datetime.datetime(2019, 1, 1, 12),
    )
    TopographyAnalysisFactory(
        subject_topography=topo1b,
        function=func1,
        task_start_time=datetime.datetime(2019, 1, 1, 13),
    )
    TopographyAnalysisFactory(
        subject_topography=topo2a,
        function=func1,
        task_start_time=datetime.datetime(2019, 1, 1, 14),
    )

    # Function should have three analyses, all successful (the default when using the factory)
    assert func1.results.count() == 3
    assert all(a.task_state == "su" for a in func1.results.all())

    # user2 shares surfaces, so user 1 should see surface1+surface2
    surface2.grant_permission(user1)

    #
    # Now we change to the analysis card view and look what we get
    #
    assert api_client.login(username=user1.username, password=password)

    response = api_client.get(
        f"{reverse('analysis:result-list')}?workflow={func1.name}"
        f"&subjects={subjects_to_base64([topo1a, topo1b, topo2a])}"
    )

    # Since analyses is shared, the user should get the same analysis
    assert func1.results.count() == 3
    assert all(a.task_state == "su" for a in func1.results.all())

    assert response.status_code == 200, response.reason_phrase

    # We should see start times of only two analysis because the third one was just
    # triggered and not yet started
    analyses = response.data["analyses"]
    assert len(analyses) == 3
    assert analyses[0]["task_start_time"] == "2019-01-01T12:00:00+01:00"  # topo1a
    assert analyses[1]["task_start_time"] == "2019-01-01T13:00:00+01:00"  # topo1b
    assert analyses[2]["task_start_time"] == "2019-01-01T14:00:00+01:00"  # topo1b

    api_client.logout()

    #
    # user 2 cannot access results from topo1, it is not shared
    #
    assert api_client.login(username=user2.username, password=password)

    response = api_client.get(
        reverse("analysis:card-series", kwargs=dict(workflow=func1.name))
        + "?subjects="
        + subjects_to_base64([topo1a, topo1b, topo2a])
    )

    assert response.status_code == 200

    # We should see start times of just one topography
    analyses = response.data["analyses"]
    assert len(analyses) == 1
    assert analyses[0]["task_start_time"] == "2019-01-01T14:00:00+01:00"  # topo2a

    api_client.logout()


@pytest.mark.django_db
def test_show_analysis_filter_with_empty_subject_list(api_client):
    user = UserFactory()

    surf1 = SurfaceFactory(created_by=user)
    surf2 = SurfaceFactory(created_by=user)

    func = Workflow.objects.get(name="topobank.testing.test")

    kwargs_1 = dict(a=2, b="abc")
    analysis1 = SurfaceAnalysisFactory(
        subject_surface=surf1, function=func, kwargs=kwargs_1
    )
    analysis2 = SurfaceAnalysisFactory(
        subject_surface=surf2, function=func, kwargs=kwargs_1
    )

    assert analysis1.subject == surf1
    assert analysis2.subject == surf2

    # Testing sending  defined subject with empty list and defined kwargs uses
    # kwargs as filter
    subjects = dict(surface=[])

    api_client.force_login(user)

    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?workflow={func.name}"
        f"&subjects={dict_to_base64(subjects)}"
        f"&kwargs={dict_to_base64(kwargs_1)}"
    )

    assert response.status_code == 200

    analyses = response.data["analyses"]
    assert len(analyses) == 2

    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?workflow={func.name}"
        f"&subjects={dict_to_base64(subjects)}"
        f"&kwargs={dict_to_base64(kwargs_1)}"
    )

    assert response.status_code == 200

    analyses = response.data["analyses"]
    assert len(analyses) == 2

    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?workflow={func.name}"
        f"&kwargs={dict_to_base64(kwargs_1)}"
    )

    assert response.status_code == 200

    analyses = response.data["analyses"]
    assert len(analyses) == 2

    response = api_client.get(
        f"{reverse('analysis:result-list')}" f"?kwargs={dict_to_base64(kwargs_1)}"
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_show_analysis_filter_without_subject_list(api_client):
    user = UserFactory()
    surf1 = SurfaceFactory(created_by=user)

    func = Workflow.objects.get(name="topobank.testing.test")

    kwargs_1 = dict(a=2, b="abc")
    analysis1 = SurfaceAnalysisFactory(
        subject_surface=surf1, function=func, kwargs=kwargs_1
    )

    assert analysis1.subject == surf1

    # Testing sending no subject but with defined kwargs uses
    # should result in error
    api_client.force_login(user)

    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?workflow={func.name}"
        f"&kwargs={dict_to_base64(kwargs_1)}"
    )

    assert response.status_code == 200, response.reason_phrase
    assert len(response.data["analyses"]) == 1


def test_set_result_permissions(
    api_client
):
    user = UserFactory()
    user2 = UserFactory()
    surf1 = SurfaceFactory(created_by=user)
    func = Workflow.objects.get(name="topobank.testing.test")
    analysis1 = SurfaceAnalysisFactory(
        subject_surface=surf1,
        function=func,
        permissions=PermissionSetFactory(
            user=user,
            allow='full'
        ),
    )
    obj = WorkflowResult.objects.get(id=analysis1.id)
    # WorkflowResult has a subject before being named
    assert obj.subject == surf1
    obj.name = "test"
    obj.save()

    obj = WorkflowResult.objects.get(id=analysis1.id)
    assert obj.subject is None  # After being named, subject is removed

    # # check user2 cannot view model
    api_client.force_login(user2)
    response = api_client.get(
        f"{reverse('analysis:named-result-list')}"
    )
    assert response.status_code == 200
    assert len(response.data) == 0

    # check user1 can view model
    api_client.force_login(user)
    response = api_client.get(
        f"{reverse('analysis:named-result-list')}"
    )

    assert response.status_code == 200
    assert len(response.data) == 1

    response = api_client.patch(
        f"{reverse('analysis:set-result-permissions', kwargs=dict(workflow_id=analysis1.id))}",
        [
            {
                "user": user2.get_absolute_url(),
                "permission": "full",
            }
        ],
    )
    assert response.status_code == 204

    # check if user1 can view model

    response = api_client.get(
        f"{reverse('analysis:named-result-list')}"
    )
    assert response.status_code == 200
    assert len(response.data) == 1

    response = api_client.patch(
        f"{reverse('analysis:set-result-permissions', kwargs=dict(workflow_id=analysis1.id))}",
        [
            {
                "user": user.get_absolute_url(),
                "permission": "no-access",
            }
        ],
    )
    assert response.status_code == 405  # Cannot remove permission from logged in user

    api_client.force_login(user2)
    response = api_client.get(
        f"{reverse('analysis:named-result-list')}"
    )
    assert response.status_code == 200
    assert len(response.data) == 1

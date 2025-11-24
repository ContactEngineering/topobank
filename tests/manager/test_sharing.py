import datetime
from pathlib import Path

import pytest
from django.shortcuts import reverse
from notifications.models import Notification

from topobank.testing.factories import (
    FIXTURE_DATA_DIR,
    SurfaceFactory,
    Topography1DFactory,
    UserFactory,
)
from topobank.testing.utils import upload_topography_file


def test_individual_read_access_permissions(
    api_client, django_user_model, handle_usage_statistics
):
    #
    # create database objects
    #
    username_1 = "A"
    username_2 = "B"
    password = "secret"

    user_1 = django_user_model.objects.create_user(
        username=username_1, password=password
    )
    user_2 = django_user_model.objects.create_user(
        username=username_2, password=password
    )

    surface = SurfaceFactory(created_by=user_1)

    surface_detail_url = reverse(
        "manager:surface-api-detail", kwargs=dict(pk=surface.pk)
    )

    #
    # now user 1 has access to surface detail page
    #
    assert api_client.login(username=username_1, password=password)
    response = api_client.get(surface_detail_url)

    assert response.status_code == 200

    api_client.logout()

    #
    # User 2 has no access
    #
    assert api_client.login(username=username_2, password=password)
    response = api_client.get(surface_detail_url)

    assert response.status_code == 404  # forbidden

    api_client.logout()

    #
    # Now grant access and user 2 should be able to access
    #

    surface.grant_permission(user_2, "view")

    assert api_client.login(username=username_2, password=password)
    response = api_client.get(surface_detail_url)

    assert response.status_code == 200  # now it's okay

    #
    # Write access is still not possible
    #
    response = api_client.patch(surface_detail_url)

    assert response.status_code == 403  # forbidden

    api_client.logout()


@pytest.mark.django_db
def test_list_surface_permissions(api_client, handle_usage_statistics):
    #
    # create database objects
    #
    password = "secret"

    user1 = UserFactory(password=password)
    user2 = UserFactory(name="Bob Marley")
    user3 = UserFactory(name="Alice Cooper")

    surface = SurfaceFactory(created_by=user1)
    surface.grant_permission(user2)
    surface.grant_permission(user3, "edit")

    surface_detail_url = reverse(
        "manager:surface-api-detail", kwargs=dict(pk=surface.pk)
    )

    #
    # now user 1 has access to surface detail page
    #
    assert api_client.login(username=user1.username, password=password)
    response = api_client.get(f"{surface_detail_url}?permissions=yes")

    # related to user 1
    assert response.data["permissions"]["current_user"][
        "user"
    ] == user1.get_absolute_url(response.wsgi_request)
    assert response.data["permissions"]["current_user"]["permission"] == "full"

    other_permissions = response.data["permissions"]["other_users"]
    assert len(other_permissions) == 2
    for permissions in other_permissions:
        if permissions["user"] == user2.get_absolute_url(response.wsgi_request):
            # related to user 2
            assert permissions["permission"] == "view"
        elif permissions["user"] == user3.get_absolute_url(response.wsgi_request):
            # related to user 3
            assert permissions["permission"] == "edit"
        else:
            assert False, "Unknown user"


@pytest.mark.django_db
def test_notification_when_deleting_shared_stuff(api_client):
    user1 = UserFactory()
    user2 = UserFactory()
    surface = SurfaceFactory(created_by=user1)
    topography = Topography1DFactory(surface=surface)

    surface.grant_permission(user2, "full")

    #
    # First: user2 deletes the topography, user1 should be notified
    #
    api_client.force_login(user2)

    response = api_client.delete(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topography.pk))
    )
    assert response.status_code == 204  # redirect

    assert (
        Notification.objects.filter(
            recipient=user1, verb="delete", description__contains=topography.name
        ).count()
        == 1
    )
    api_client.logout()

    #
    # Second: user1 deletes the surface, user2 should be notified
    #
    api_client.force_login(user1)

    response = api_client.delete(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface.pk))
    )
    assert response.status_code == 204  # redirect

    assert (
        Notification.objects.filter(
            recipient=user2, verb="delete", description__contains=surface.name
        ).count()
        == 1
    )
    api_client.logout()


@pytest.mark.django_db
def test_upload_topography_for_shared_surface(
    api_client, settings, handle_usage_statistics, django_capture_on_commit_callbacks
):
    input_file_path = Path(FIXTURE_DATA_DIR + "/example3.di")
    description = "test description"

    password = "abcd$1234"

    user1 = UserFactory(password=password)
    user2 = UserFactory(password=password)

    surface = SurfaceFactory(created_by=user1)
    surface.grant_permission(user2)  # first without allowing change

    assert api_client.login(username=user2.username, password=password)

    #
    # open first step of wizard: file upload
    #
    response = api_client.post(
        reverse("manager:topography-api-list"),
        {
            "surface": reverse(
                "manager:surface-api-detail", kwargs=dict(pk=surface.id)
            ),
            "name": "example3.di",
        },
    )
    assert response.status_code == 403  # user2 is not allowed to change

    #
    # Now allow to change and get response again
    #
    surface.grant_permission(user2, "edit")
    api_client.force_login(user2)
    response = upload_topography_file(
        str(input_file_path),
        surface.id,
        api_client,
        django_capture_on_commit_callbacks,
        **{
            "description": description,
        },
    )
    assert response.data["name"] == "example3.di"
    assert response.data["channel_names"] == [
        ["ZSensor", "nm"],
        ["AmplitudeError", None],
        ["Phase", None],
        ["Height", "nm"],
    ]

    topos = surface.topography_set.all()

    assert len(topos) == 1

    t = topos[0]

    assert t.measurement_date == datetime.date(2014, 12, 15)
    assert t.description == description
    assert "example3" in t.datafile.filename
    assert 256 == t.resolution_x
    assert 256 == t.resolution_y
    assert t.created_by == user2

    #
    # Test little badge which shows who uploaded data
    #
    response = api_client.get(
        reverse("manager:topography-api-detail", kwargs=dict(pk=t.pk))
    )
    assert response.status_code == 200
    api_client.logout()

    assert api_client.login(username=user1.username, password=password)
    response = api_client.get(
        reverse("manager:topography-api-detail", kwargs=dict(pk=t.pk))
    )
    assert response.status_code == 200
    api_client.logout()

    #
    # There should be a notification of the user
    #
    # exp_mesg = (
    #     f"User '{user2}' added the measurement '{t.name}' to digital surface twin "
    #     f"'{t.surface.name}'."
    # )
    # assert (
    #     Notification.objects.filter(
    #         unread=True, recipient=user1, verb="create", description__contains=exp_mesg
    #     ).count()
    #     == 1
    # )

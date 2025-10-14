from pathlib import Path

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse

from topobank.authorization.models import PermissionSet
from topobank.manager.models import Surface, Topography
from topobank.testing.data import FIXTURE_DATA_DIR


@pytest.mark.django_db
def test_prevent_surface_access_by_other_user(
    api_client, django_user_model, handle_usage_statistics
):
    surface_id = 1
    username1 = "testuser1"
    password1 = "abcd$1234"
    username2 = "testuser2"
    password2 = "abcd$5678"

    #
    # Create surface of user 1
    #
    user1 = django_user_model.objects.create_user(
        username=username1, password=password1
    )

    surface = Surface.objects.create(id=surface_id, name="Surface 1", creator=user1)
    assert surface.id == surface_id
    surface.save()

    #
    # Login as user 2
    #
    user2 = django_user_model.objects.create_user(
        username=username2, password=password2
    )
    assert api_client.login(username=username2, password=password2)

    # give both user permissions to skip all terms, we want to test independently from this
    skip_perm = Permission.objects.get(codename="can_skip_terms")
    user1.user_permissions.add(skip_perm)
    user2.user_permissions.add(skip_perm)

    #
    # As user 2, try to access surface from user 1 with various views
    #
    # Each time, this should redirect to an access denied page
    #
    response = api_client.get(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface_id))
    )
    assert response.status_code == 404

    response = api_client.patch(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface_id))
    )
    assert response.status_code == 404

    response = api_client.delete(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface_id))
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_prevent_topography_access_by_other_user(
    api_client, django_user_model, mocker, handle_usage_statistics
):
    surface_id = 1
    username1 = "testuser1"
    password1 = "abcd$1234"
    username2 = "testuser2"
    password2 = "abcd$5678"

    #
    # Create surface of user 1
    #
    user1 = django_user_model.objects.create_user(
        username=username1, password=password1
    )

    surface = Surface.objects.create(
        id=surface_id,
        name="Surface 1",
        creator=user1,
        permissions=PermissionSet.objects.create(),
    )
    assert surface.id == surface_id
    surface.save()
    surface.grant_permission(user1, "edit")

    #
    # Mock a topography
    #
    input_file_path = Path(FIXTURE_DATA_DIR + "/example3.di")

    # prevent signals when creating topography
    mocker.patch("django.db.models.signals.pre_save.send")
    mocker.patch("django.db.models.signals.post_save.send")
    topography = Topography.objects.create(
        name="topo",
        surface=surface,
        measurement_date="2018-01-01",
        data_source=0,
        size_x=1,
        size_y=1,
        resolution_x=1,
        resolution_y=1,
    )
    topography.save_datafile(open(input_file_path, "rb"))
    topography_id = topography.id

    #
    # Login as user 1
    #
    assert api_client.login(username=username1, password=password1)
    response = api_client.get(
        reverse("manager:topography-v2-detail", kwargs=dict(pk=topography_id))
    )
    assert response.status_code == 200
    assert response.data["permissions"]["allow"] == "edit"

    #
    # Login as user 2
    #
    django_user_model.objects.create_user(username=username2, password=password2)
    assert api_client.login(username=username2, password=password2)

    #
    # As user 2, try to access topography from user 1 with various views
    #
    # Each time, this should redirect to an access denied page
    #
    response = api_client.get(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topography_id))
    )
    assert response.status_code == 404

    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topography_id))
    )
    assert response.status_code == 404

    response = api_client.delete(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topography_id))
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_pagenotfound_if_surface_does_not_exist(
    api_client, django_user_model, handle_usage_statistics
):
    username = "testuser1"
    password = "abcd$1234"

    django_user_model.objects.create_user(username=username, password=password)

    assert api_client.login(username=username, password=password)

    response = api_client.get(
        reverse("manager:surface-api-detail", kwargs=dict(pk=999))
    )
    assert response.status_code == 404

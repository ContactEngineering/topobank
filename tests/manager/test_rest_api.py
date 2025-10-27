import json

import numpy
import pytest
from rest_framework.reverse import reverse

from topobank.manager.models import Surface, Topography
from topobank.testing.factories import SurfaceFactory, TagFactory
from topobank.testing.utils import (
    ASSERT_EQUAL_IGNORE_VALUE,
    assert_dict_equal,
    assert_dicts_equal,
)
from topobank.users.anonymous import get_anonymous_user


@pytest.mark.django_db
@pytest.mark.parametrize(
    "is_authenticated,with_children", [[True, False], [False, False], [True, True]]
)
def test_surface_retrieve_routes(
    api_client, is_authenticated, with_children, two_topos, handle_usage_statistics
):
    topo1, topo2 = two_topos
    user = topo1.creator
    assert topo2.creator == user

    surface1 = topo1.surface
    surface2 = topo2.surface

    anonymous_user = get_anonymous_user()
    assert surface1.get_permission(anonymous_user) is None
    assert surface2.get_permission(anonymous_user) is None
    assert surface1.get_permission(user) == "full"
    assert surface2.get_permission(user) == "full"

    if is_authenticated:
        api_client.force_authenticate(user)

    response = api_client.get(reverse("manager:surface-api-list"))
    assert response.status_code == 200

    topography_api_list_url = reverse(
        "manager:topography-api-list", request=response.wsgi_request
    )
    surface1_dict = {
        "category": None,
        "creator": f"http://testserver/users/v1/user/{user.id}/",
        "description": "",
        "name": "Surface 1",
        "id": surface1.id,
        "tags": [],
        "url": f"http://testserver/manager/api/surface/{surface1.id}/",
        "api": {
            "set_permissions": ASSERT_EQUAL_IGNORE_VALUE,
            "download": ASSERT_EQUAL_IGNORE_VALUE,
            "async_download": ASSERT_EQUAL_IGNORE_VALUE,
        },
        "creation_datetime": surface1.creation_time.astimezone().isoformat(),
        "modification_datetime": surface1.modification_time.astimezone().isoformat(),
        "attachments": surface1.attachments.get_absolute_url(response.wsgi_request),
        "topographies": f"{topography_api_list_url}?surface={surface1.id}",
        "properties": {},
        "permissions": ASSERT_EQUAL_IGNORE_VALUE,
        "topography_set": ASSERT_EQUAL_IGNORE_VALUE,
    }
    if hasattr(Surface, "publication"):
        surface1_dict["publication"] = None
    surface1_topographies_dict = [
        {
            "attachments": topo1.attachments.get_absolute_url(response.wsgi_request),
            "bandwidth_lower": topo1.bandwidth_lower,
            "bandwidth_upper": topo1.bandwidth_upper,
            "creator": f"http://testserver/users/v1/user/{user.id}/",
            "datafile_format": topo1.datafile_format,
            "description": "description1",
            "detrend_mode": "height",
            "fill_undefined_data_mode": "do-not-fill",
            "has_undefined_data": False,
            "height_scale": 0.296382712790741,
            "height_scale_editable": False,
            "instrument_name": "",
            "instrument_parameters": {},
            "instrument_type": "undefined",
            "is_periodic": False,
            "is_periodic_editable": True,
            "measurement_date": "2018-01-01",
            "name": "Example 3 - ZSensor",
            "resolution_x": 256,
            "resolution_y": 256,
            "short_reliability_cutoff": None,
            "size_editable": False,
            "size_x": 10000.0,
            "size_y": 10000.0,
            "surface": f"http://testserver/manager/api/surface/{surface1.id}/",
            "unit": "nm",
            "unit_editable": False,
            "url": f"http://testserver/manager/api/topography/{topo1.id}/",
            "api": {
                "force_inspect": ASSERT_EQUAL_IGNORE_VALUE,
            },
            "task_duration": None,
            "task_error": None,
            "id": topo1.id,
            "datafile": ASSERT_EQUAL_IGNORE_VALUE,
            "squeezed_datafile": ASSERT_EQUAL_IGNORE_VALUE,
            "deepzoom": ASSERT_EQUAL_IGNORE_VALUE,
            "tags": [],
            "task_progress": 0.0,
            "task_state": "pe",
            "thumbnail": ASSERT_EQUAL_IGNORE_VALUE,
            "channel_names": [],
            "data_source": 0,
            "is_metadata_complete": True,
            "creation_datetime": topo1.creation_time.astimezone().isoformat(),
            "modification_datetime": topo1.modification_time.astimezone().isoformat(),
            "permissions": ASSERT_EQUAL_IGNORE_VALUE,
        }
    ]
    surface2_dict = {
        "category": None,
        "creator": f"http://testserver/users/v1/user/{user.id}/",
        "description": "",
        "name": "Surface 2",
        "id": surface2.id,
        "tags": [],
        "url": f"http://testserver/manager/api/surface/{surface2.id}/",
        "api": {
            "set_permissions": ASSERT_EQUAL_IGNORE_VALUE,
            "download": ASSERT_EQUAL_IGNORE_VALUE,
            "async_download": ASSERT_EQUAL_IGNORE_VALUE,
        },
        "creation_datetime": surface2.creation_time.astimezone().isoformat(),
        "modification_datetime": surface2.modification_time.astimezone().isoformat(),
        "attachments": surface2.attachments.get_absolute_url(response.wsgi_request),
        "topographies": f"{topography_api_list_url}?surface={surface2.id}",
        "properties": {},
        "permissions": ASSERT_EQUAL_IGNORE_VALUE,
        "topography_set": ASSERT_EQUAL_IGNORE_VALUE,
    }
    if hasattr(Surface, "publication"):
        surface2_dict["publication"] = None
    surface2_topographies_dict = [
        {
            "attachments": topo2.attachments.get_absolute_url(response.wsgi_request),
            "bandwidth_lower": topo2.bandwidth_lower,
            "bandwidth_upper": topo2.bandwidth_upper,
            "creator": f"http://testserver/users/v1/user/{user.id}/",
            "datafile_format": topo2.datafile_format,
            "description": "description2",
            "detrend_mode": "height",
            "fill_undefined_data_mode": "do-not-fill",
            "has_undefined_data": False,
            "height_scale": 2.91818e-08,
            "height_scale_editable": False,
            "instrument_name": "",
            "instrument_parameters": {},
            "instrument_type": "undefined",
            "is_periodic": False,
            "is_periodic_editable": True,
            "measurement_date": "2018-01-02",
            "name": "Example 4 - Default",
            "resolution_x": 75,
            "resolution_y": 305,
            "short_reliability_cutoff": None,
            "size_editable": False,
            "size_y": 112.80791e-6,
            "size_x": 27.73965e-6,
            "surface": f"http://testserver/manager/api/surface/{surface2.id}/",
            "unit": "m",
            "unit_editable": False,
            "url": f"http://testserver/manager/api/topography/{topo2.id}/",
            "api": {
                "force_inspect": ASSERT_EQUAL_IGNORE_VALUE,
            },
            "task_duration": None,
            "task_error": None,
            "id": topo2.id,
            "datafile": ASSERT_EQUAL_IGNORE_VALUE,
            "squeezed_datafile": ASSERT_EQUAL_IGNORE_VALUE,
            "deepzoom": ASSERT_EQUAL_IGNORE_VALUE,
            "thumbnail": ASSERT_EQUAL_IGNORE_VALUE,
            "tags": [],
            "task_progress": 0.0,
            "task_state": "pe",
            "channel_names": [],
            "data_source": 0,
            "is_metadata_complete": True,
            "creation_datetime": topo2.creation_time.astimezone().isoformat(),
            "modification_datetime": topo2.modification_time.astimezone().isoformat(),
            "permissions": ASSERT_EQUAL_IGNORE_VALUE,
        }
    ]

    if with_children:
        surface1_dict["topography_set"] = surface1_topographies_dict
        surface2_dict["topography_set"] = surface2_topographies_dict

    url = reverse("manager:surface-api-detail", kwargs=dict(pk=surface1.id))
    if with_children:
        url += "?children=yes"
    response = api_client.get(url)
    if is_authenticated:
        assert response.status_code == 200
        data = json.loads(json.dumps(response.data))  # Convert OrderedDict to dict
        assert_dict_equal(data, surface1_dict)

        response = api_client.get(
            f"{reverse('manager:topography-api-list')}?surface={surface1.id}"
        )
        data = response.data
        assert_dicts_equal(data, surface1_topographies_dict)
    else:
        # Anonymous user does not have access by default
        assert response.status_code == 404

    url = reverse("manager:surface-api-detail", kwargs=dict(pk=surface2.id))
    if with_children:
        url += "?children=yes"
    response = api_client.get(url)
    if is_authenticated:
        assert response.status_code == 200
        data = json.loads(json.dumps(response.data))  # Convert OrderedDict to dict
        assert_dict_equal(data, surface2_dict)

        response = api_client.get(
            f"{reverse('manager:topography-api-list')}?surface={surface2.id}"
        )
        data = response.data
        assert_dicts_equal(data, surface2_topographies_dict)
    else:
        # Anonymous user does not have access by default
        assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize("is_authenticated", [True, False])
def test_topography_retrieve_routes(
    api_client, is_authenticated, two_topos, handle_usage_statistics
):
    topo1, topo2 = two_topos
    user = topo1.creator
    assert topo2.creator == user

    topo1.surface.tags = ["my/super/tag", "my/super"]
    topo1.surface.save()
    topo2.surface.tags = ["my/super"]
    topo2.surface.save()

    anonymous_user = get_anonymous_user()
    assert not topo1.has_permission(anonymous_user, "view")
    assert topo1.has_permission(user, "view")

    if is_authenticated:
        api_client.force_authenticate(user)

    response = api_client.get(reverse("manager:topography-api-list"))
    assert response.status_code == 400

    response = api_client.get(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topo1.id))
    )

    topo1_dict = {
        "bandwidth_lower": topo1.bandwidth_lower,
        "bandwidth_upper": topo1.bandwidth_upper,
        "creator": f"http://testserver/users/v1/user/{user.id}/",
        "datafile_format": topo1.datafile_format,
        "description": "description1",
        "detrend_mode": "height",
        "fill_undefined_data_mode": "do-not-fill",
        "has_undefined_data": False,
        "height_scale": 0.296382712790741,
        "height_scale_editable": False,
        "instrument_name": "",
        "instrument_parameters": {},
        "instrument_type": "undefined",
        "is_periodic": False,
        "is_periodic_editable": True,
        "measurement_date": "2018-01-01",
        "name": "Example 3 - ZSensor",
        "resolution_x": 256,
        "resolution_y": 256,
        "short_reliability_cutoff": None,
        "size_editable": False,
        "size_x": 10000.0,
        "size_y": 10000.0,
        "surface": f"http://testserver/manager/api/surface/{topo1.surface.id}/",
        "unit": "nm",
        "unit_editable": False,
        "url": f"http://testserver/manager/api/topography/{topo1.id}/",
        "api": {
            "force_inspect": ASSERT_EQUAL_IGNORE_VALUE,
        },
        "tags": [],
        "task_progress": 0.0,
        "task_state": "pe",
        "thumbnail": ASSERT_EQUAL_IGNORE_VALUE,
        "is_metadata_complete": True,
        "id": topo1.id,
        "task_error": None,
        "task_duration": None,
        "data_source": 0,
        "channel_names": [
            ["ZSensor", "nm"],
            ["AmplitudeError", None],
            ["Phase", None],
            ["Height", "nm"],
        ],
        "creation_datetime": topo1.creation_time.astimezone().isoformat(),
        "modification_datetime": topo1.modification_time.astimezone().isoformat(),
        "attachments": topo1.attachments.get_absolute_url(response.wsgi_request),
        "deepzoom": ASSERT_EQUAL_IGNORE_VALUE,
        "datafile": ASSERT_EQUAL_IGNORE_VALUE,
        "squeezed_datafile": ASSERT_EQUAL_IGNORE_VALUE,
        "permissions": {
            "current_user": {
                "user": user.get_absolute_url(response.wsgi_request),
                "permission": "full",
            },
            "other_users": [],
        },
    }
    topo2_dict = {
        "bandwidth_lower": topo2.bandwidth_lower,
        "bandwidth_upper": topo2.bandwidth_upper,
        "creator": f"http://testserver/users/v1/user/{user.id}/",
        "datafile_format": topo2.datafile_format,
        "description": "description2",
        "detrend_mode": "height",
        "fill_undefined_data_mode": "do-not-fill",
        "has_undefined_data": False,
        "height_scale": 2.91818e-08,
        "height_scale_editable": False,
        "instrument_name": "",
        "instrument_parameters": {},
        "instrument_type": "undefined",
        "is_periodic": False,
        "is_periodic_editable": True,
        "measurement_date": "2018-01-02",
        "name": "Example 4 - Default",
        "resolution_x": 75,
        "resolution_y": 305,
        "short_reliability_cutoff": None,
        "size_editable": False,
        "size_y": 112.80791e-6,
        "size_x": 27.73965e-6,
        "surface": f"http://testserver/manager/api/surface/{topo2.surface.id}/",
        "unit": "m",
        "unit_editable": False,
        "url": f"http://testserver/manager/api/topography/{topo2.id}/",
        "api": {
            "force_inspect": ASSERT_EQUAL_IGNORE_VALUE,
        },
        "tags": [],
        "task_progress": 0.0,
        "task_state": "pe",
        "thumbnail": ASSERT_EQUAL_IGNORE_VALUE,
        "is_metadata_complete": True,
        "id": topo2.id,
        "task_error": None,
        "task_duration": None,
        "data_source": 0,
        "channel_names": [],
        "creation_datetime": topo2.creation_time.astimezone().isoformat(),
        "modification_datetime": topo2.modification_time.astimezone().isoformat(),
        "attachments": topo2.attachments.get_absolute_url(response.wsgi_request),
        "deepzoom": ASSERT_EQUAL_IGNORE_VALUE,
        "datafile": ASSERT_EQUAL_IGNORE_VALUE,
        "squeezed_datafile": ASSERT_EQUAL_IGNORE_VALUE,
        "permissions": {
            "current_user": {
                "user": user.get_absolute_url(response.wsgi_request),
                "permission": "full",
            },
            "other_users": [],
        },
    }

    if is_authenticated:
        assert response.status_code == 200
        data = json.loads(json.dumps(response.data))  # Convert OrderedDict to dict
        # topo1 is updated but the get command, because it is triggering file inspection
        topo1 = Topography.objects.get(pk=topo1.id)
        topo1_dict["modification_datetime"] = (
            topo1.modification_time.astimezone().isoformat()
        )
        assert_dict_equal(data, topo1_dict)
    else:
        # Anonymous user does not have access by default
        assert response.status_code == 404

    response = api_client.get(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topo2.id))
    )
    if is_authenticated:
        assert response.status_code == 200
        data = json.loads(json.dumps(response.data))  # Convert OrderedDict to dict
        # topo2 is updated but the get command, because it is triggering file inspection
        topo2 = Topography.objects.get(pk=topo2.id)
        topo2_dict["modification_datetime"] = (
            topo2.modification_time.astimezone().isoformat()
        )
        assert_dict_equal(data, topo2_dict)
    else:
        # Anonymous user does not have access by default
        assert response.status_code == 404

    response = api_client.get(
        f'{reverse("manager:topography-api-list")}?tag_startswith=my/super'
    )
    if is_authenticated:
        assert len(response.data) == 2
    else:
        assert len(response.data) == 0


@pytest.mark.django_db
def test_create_surface_routes(api_client, two_users, handle_usage_statistics):
    (user1, user2), (surface1, surface2, surface3) = two_users

    surface1_dict = {"name": "Surface 1", "description": "This is surface 1"}

    # Create as anonymous user should fail
    response = api_client.post(
        reverse("manager:surface-api-list"), data=surface1_dict, format="json"
    )
    assert response.status_code == 403

    assert Surface.objects.count() == 3

    # Create as user1 should succeed
    api_client.force_authenticate(user1)
    response = api_client.post(
        reverse("manager:surface-api-list"), data=surface1_dict, format="json"
    )
    assert response.status_code == 201

    assert Surface.objects.count() == 4
    s = Surface.objects.get(id=response.data["id"])
    assert s.creator.name == user1.name


@pytest.mark.django_db
def test_delete_surface_routes(api_client, two_users, handle_usage_statistics):
    (user1, user2), (surface1, surface2, surface3) = two_users
    topo1, topo2, topo3 = Topography.objects.all()
    user = topo1.creator
    surface1 = topo1.surface
    surface2 = topo2.surface

    # Delete as anonymous user should fail
    response = api_client.delete(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface1.id))
    )
    assert response.status_code == 403

    assert Surface.objects.count() == 3

    # Delete as user should succeed
    api_client.force_authenticate(user)
    response = api_client.delete(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface1.id))
    )
    assert response.status_code == 204  # Success, no content

    assert Surface.objects.count() == 2

    # Delete of a surface of another user should fail
    response = api_client.delete(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface2.id))
    )
    assert response.status_code == 404  # The user cannot see the surface, hence 404

    assert Surface.objects.count() == 2

    # Delete of a surface of another user should fail, even if shared
    surface2.grant_permission(user1, "view")
    response = api_client.delete(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface2.id))
    )
    assert (
        response.status_code == 403
    )  # The user can see the surface but not delete it, hence 403

    assert Surface.objects.count() == 2

    # Delete of a surface of another user should fail even if shared with write permission
    surface2.grant_permission(user1, "edit")
    response = api_client.delete(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface2.id))
    )
    assert (
        response.status_code == 403
    )  # The user can see the surface but not delete it, hence 403
    assert Surface.objects.count() == 2

    # Delete of a surface of another user is possible with full access
    surface2.grant_permission(user, "full")
    response = api_client.delete(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface2.id))
    )
    assert (
        response.status_code == 204
    )  # The user can see the surface but not delete it, hence 403
    assert Surface.objects.count() == 1


@pytest.mark.django_db
def test_delete_topography_routes(api_client, two_topos, handle_usage_statistics):
    topo1, topoe2 = two_topos
    user = topo1.creator

    # Delete as anonymous user should fail
    response = api_client.delete(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topo1.id)),
        format="json",
    )
    assert response.status_code == 403

    assert Topography.objects.count() == 2

    # Delete as user should succeed
    api_client.force_authenticate(user)
    response = api_client.delete(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topo1.id)),
        format="json",
    )
    assert response.status_code == 204  # Success, no content

    assert Topography.objects.count() == 1


@pytest.mark.django_db
def test_patch_surface_routes(api_client, two_topos, handle_usage_statistics):
    topo1, topo2 = two_topos
    user = topo1.creator
    surface1 = topo1.surface
    surface2 = topo2.surface

    new_name = "My new name"

    # Patch as anonymous user should fail
    response = api_client.patch(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface1.id)),
        data={"name": new_name},
        format="json",
    )
    assert response.status_code == 403

    assert Surface.objects.count() == 2

    # Patch as user should succeed
    api_client.force_authenticate(user)
    response = api_client.patch(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface1.id)),
        data={"name": new_name},
        format="json",
    )
    assert response.status_code == 200  # Success, no content

    assert Surface.objects.count() == 2

    surface1, surface2 = Surface.objects.all()
    assert surface1.name == new_name

    assert surface1.modification_time > surface1.creation_time


@pytest.mark.django_db
def test_patch_topography_routes(api_client, two_users, handle_usage_statistics):
    (user1, user2), (surface1, surface2, surface3) = two_users
    topo1, topo2, topo3 = Topography.objects.all()
    assert topo1.creator == user1

    new_name = "My new name"

    # Patch as anonymous user should fail
    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topo1.id)),
        data={"name": new_name},
        format="json",
    )
    assert response.status_code == 403

    assert Topography.objects.count() == 3

    # Patch as user should succeed
    api_client.force_authenticate(user1)
    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topo1.id)),
        data={"name": new_name},
        format="json",
    )
    assert response.status_code == 200  # Success, no content

    assert Topography.objects.count() == 3
    topo1, topo2, topo3 = Topography.objects.all()
    assert topo1.name == new_name
    assert topo1.modification_time > topo1.creation_time

    new_name = "My second new name"

    # Patch of a topography of another user should fail
    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topo2.id)),
        data={"name": new_name},
        format="json",
    )
    assert response.status_code == 404  # The user cannot see the surface, hence 404

    assert Topography.objects.count() == 3

    # Patch of a topography of another user should fail, even if shared
    topo2.surface.grant_permission(user1, "view")
    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topo2.id)),
        {"name": new_name},
    )
    assert (
        response.status_code == 403
    )  # The user can see the surface but not patch it, hence 403

    assert Topography.objects.count() == 3

    # Patch of a surface of another user should succeed if shared with write permission
    topo2.surface.grant_permission(user1, "edit")
    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topo2.id)),
        {"name": new_name},
    )
    assert response.status_code == 200  # Success, no content
    assert Topography.objects.count() == 3
    topo1, topo2, topo3 = Topography.objects.all()
    assert topo2.name == new_name

    # Patching surface field of a topography should fail
    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topo2.id)),
        {
            "surface": reverse(
                "manager:surface-api-detail", kwargs=dict(pk=topo1.surface.id)
            )
        },
    )
    assert (
        response.status_code == 400
    )  # The user can see the surface but not patch it, hence 400
    assert Topography.objects.count() == 3
    topo1, topo2, topo3 = Topography.objects.all()
    assert topo2.name == new_name
    surface1, surface2, surface3 = Surface.objects.all()
    assert surface1.topography_set.count() == 1
    assert surface2.topography_set.count() == 1
    assert surface3.topography_set.count() == 1


def test_versions(api_client):
    response = api_client.get(reverse("manager:versions"))
    assert response.data["numpy"] == {
        "version": numpy.__version__,
        "license": "BSD 3-Clause",
        "homepage": "https://numpy.org/",
    }


@pytest.mark.django_db
def test_statistics(api_client, two_users, user_staff, handle_usage_statistics):
    response = api_client.get(reverse("manager:statistics"))
    assert "nb_users" not in response.data
    api_client.force_login(user_staff)
    response = api_client.get(reverse("manager:statistics"))
    assert response.data["nb_users"] == 3
    assert response.data["nb_surfaces"] == 3
    assert response.data["nb_topographies"] == 3


@pytest.mark.django_db
def test_statistics2(api_client, test_instances, handle_usage_statistics):
    (user_1, user_2), (surface_1, surface_2), (topography_1,) = test_instances
    surface_2.grant_permission(user_2)

    #
    # Test statistics if user_1 is authenticated
    #
    api_client.force_login(user_1)
    response = api_client.get(reverse("manager:statistics"))

    assert response.data["nb_users"] == 2
    assert response.data["nb_surfaces"] == 2
    assert response.data["nb_surfaces_of_user"] == 2
    assert response.data["nb_topographies"] == 1
    assert response.data["nb_topographies_of_user"] == 1
    assert response.data["nb_surfaces_shared_with_user"] == 0

    response = api_client.get(reverse("analysis:statistics"))

    assert response.data["nb_analyses"] == 1
    assert response.data["nb_analyses_of_user"] == 1

    api_client.logout()

    #
    # Test statistics if user_2 is authenticated
    #
    api_client.force_login(user_2)
    response = api_client.get(reverse("manager:statistics"))

    assert response.data["nb_users"] == 2
    assert response.data["nb_surfaces"] == 2
    assert response.data["nb_surfaces_of_user"] == 1
    assert response.data["nb_topographies"] == 1
    assert response.data["nb_topographies_of_user"] == 0
    assert response.data["nb_surfaces_shared_with_user"] == 1

    response = api_client.get(reverse("analysis:statistics"))

    assert response.data["nb_analyses"] == 1
    assert response.data["nb_analyses_of_user"] == 0

    api_client.logout()


def test_tag_retrieve_routes(api_client, two_users, handle_usage_statistics):
    (user1, user2), (surface1, surface2, surface3) = two_users

    st = TagFactory(surfaces=[surface2, surface3])
    tag1 = surface2.tags.first()

    # Anonymous user should not be able to see the tag
    response = api_client.get(
        reverse("manager:tag-api-detail", kwargs=dict(name=st.name))
    )
    assert response.status_code == 403

    # User 1 should not be able to see the tag because she has no access to the two
    # surfaces that are tagged, hence the tag does not exist for her
    api_client.force_login(user1)
    response = api_client.get(
        f"{reverse('manager:tag-api-detail', kwargs=dict(name=st.name))}?surfaces=yes"
    )
    assert response.status_code == 403

    # List API without query parameters should not fail
    response = api_client.get(reverse("manager:surface-api-list"))
    assert response.status_code == 200

    # Try to grab all surfaces without tags
    response = api_client.get(f"{reverse('manager:surface-api-list')}?tag=")
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["id"] == surface1.id

    # List top-level tags
    response = api_client.get(reverse("manager:tag-api-list"))
    assert response.status_code == 200
    assert response.data == [""]

    # User 2 has access to all surfaces inside the tag
    api_client.force_login(user2)
    response = api_client.get(
        reverse("manager:tag-api-detail", kwargs=dict(name=st.name))
    )
    assert response.data["name"] == st.name

    response = api_client.get(f"{reverse('manager:surface-api-list')}?tag={st.name}")
    topography_api_list_url = reverse(
        "manager:topography-api-list", request=response.wsgi_request
    )
    assert_dicts_equal(
        response.data,
        [
            {
                "url": surface3.get_absolute_url(response.wsgi_request),
                "api": {
                    "set_permissions": ASSERT_EQUAL_IGNORE_VALUE,
                    "download": ASSERT_EQUAL_IGNORE_VALUE,
                    "async_download": ASSERT_EQUAL_IGNORE_VALUE,
                },
                "id": surface3.id,
                "name": surface3.name,
                "category": None,
                "creator": surface2.creator.get_absolute_url(response.wsgi_request),
                "description": "",
                "tags": [st.name],
                "creation_datetime": surface3.creation_time.astimezone().isoformat(),
                "modification_datetime": surface3.modification_time.astimezone().isoformat(),
                "attachments": surface3.attachments.get_absolute_url(
                    response.wsgi_request
                ),
                "topographies": f"{topography_api_list_url}?surface={surface3.id}",
                "properties": {},
                "topography_set": ASSERT_EQUAL_IGNORE_VALUE,
                "permissions": ASSERT_EQUAL_IGNORE_VALUE,
            },
            {
                "url": surface2.get_absolute_url(response.wsgi_request),
                "api": {
                    "set_permissions": ASSERT_EQUAL_IGNORE_VALUE,
                    "download": ASSERT_EQUAL_IGNORE_VALUE,
                    "async_download": ASSERT_EQUAL_IGNORE_VALUE,
                },
                "id": surface2.id,
                "name": surface2.name,
                "category": None,
                "creator": surface2.creator.get_absolute_url(response.wsgi_request),
                "description": "",
                "tags": [st.name],
                "creation_datetime": surface2.creation_time.astimezone().isoformat(),
                "modification_datetime": surface2.modification_time.astimezone().isoformat(),
                "attachments": surface2.attachments.get_absolute_url(
                    response.wsgi_request
                ),
                "topographies": f"{topography_api_list_url}?surface={surface2.id}",
                "properties": {},
                "topography_set": ASSERT_EQUAL_IGNORE_VALUE,
                "permissions": ASSERT_EQUAL_IGNORE_VALUE,
            },
        ],
    )

    response = api_client.get(reverse("manager:tag-api-list"))
    assert response.status_code == 200
    assert set(response.data) == {
        surface2.tags.first().name,
        surface3.tags.first().name,
    }

    surface2.tags.add("My/fant&astic/tag")
    surface3.tags.add("My/fant&astic/tag")
    surface2.tags.add("My/fant&astic-four/tag")

    response = api_client.get(reverse("manager:tag-api-detail", kwargs=dict(name="My")))
    assert response.status_code == 200
    assert response.data["name"] == "My"
    assert set(response.data["children"]) == {"My/fant&astic", "My/fant&astic-four"}

    response = api_client.get(
        f"{reverse('manager:tag-api-detail', kwargs=dict(name='My/fant&astic'))}?surfaces=yes"
    )
    assert response.status_code == 200
    assert response.data["name"] == "My/fant&astic"
    assert response.data["children"] == ["My/fant&astic/tag"]

    response = api_client.get(
        f"{reverse('manager:surface-api-list')}?tag=My/fant&astic"
    )
    assert len(response.data) == 0

    response = api_client.get(
        f"{reverse('manager:tag-api-detail', kwargs=dict(name='My/fant&astic/tag'))}?surfaces=yes"
    )
    assert response.status_code == 200
    assert response.data["name"] == "My/fant&astic/tag"
    assert response.data["children"] == []

    response = api_client.get(
        f"{reverse('manager:surface-api-list')}?tag=My/fant%26astic/tag"
    )
    assert len(response.data) == 2

    # Check top-level tags
    response = api_client.get(reverse("manager:tag-api-list"))
    assert response.status_code == 200
    assert response.data == ["My", st.name]

    # Login as user1
    api_client.force_login(user1)
    response = api_client.get(reverse("manager:tag-api-detail", kwargs=dict(name="My")))
    assert response.status_code == 403

    # Share surface2 with user1
    surface2.grant_permission(user1, "view")
    response = api_client.get(reverse("manager:tag-api-detail", kwargs=dict(name="My")))
    assert response.status_code == 200

    # Check top-level tags
    response = api_client.get(reverse("manager:tag-api-list"))
    assert response.status_code == 200
    # Make sure "None" is not in this list
    assert set(response.data) == {"", "My", tag1.name}


def test_create_topography(api_client, user_alice, handle_usage_statistics):
    surface = SurfaceFactory(creator=user_alice)

    # Not logged in
    response = api_client.post(
        reverse("manager:topography-api-list"),
        {
            "surface": reverse(
                "manager:surface-api-detail", kwargs=dict(pk=surface.id)
            ),
            "name": "My name",
        },
    )
    assert response.status_code == 403

    api_client.force_login(user_alice)

    # Existing surface id
    response = api_client.post(
        reverse("manager:topography-api-list"),
        {
            "surface": reverse(
                "manager:surface-api-detail", kwargs=dict(pk=surface.id)
            ),
            "name": "My name",
        },
    )
    assert response.status_code == 201

    # Nonexisting surface id
    response = api_client.post(
        reverse("manager:topography-api-list"),
        {
            "surface": reverse(
                "manager:surface-api-detail", kwargs=dict(pk=surface.id + 101)
            ),
            "name": "My name",
        },
    )
    assert response.status_code == 400


def test_create_topography_with_blank_name_fails(
    api_client, user_alice, handle_usage_statistics
):
    surface = SurfaceFactory(creator=user_alice)
    api_client.force_login(user_alice)

    # Existing surface id
    response = api_client.post(
        reverse("manager:topography-api-list"),
        {
            "surface": reverse(
                "manager:surface-api-detail", kwargs=dict(pk=surface.id)
            ),
            "name": "",
        },
    )
    assert response.status_code == 400


def test_set_surface_permissions_user(
    api_client, user_alice, user_bob, handle_usage_statistics
):
    surface = SurfaceFactory(creator=user_alice)
    surface.grant_permission(user_alice, "full")

    api_client.force_login(user_bob)
    response = api_client.get(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface.id))
    )
    assert response.status_code == 404

    api_client.force_login(user_alice)
    response = api_client.patch(
        reverse("manager:set-surface-permissions", kwargs=dict(pk=surface.id)),
        [
            {
                "user": user_bob.get_absolute_url(response.wsgi_request),
                "permission": "full",
            }
        ],
    )
    assert response.status_code == 204

    api_client.force_login(user_bob)
    response = api_client.get(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface.id))
    )
    assert response.status_code == 200

    set_permissions_url = response.data["api"]["set_permissions"]
    response = api_client.patch(
        set_permissions_url,
        [
            {
                "user": user_bob.get_absolute_url(response.wsgi_request),
                "permission": "no-access",
            }
        ],
    )
    assert response.status_code == 405  # Cannot remove permission from logged in user

    response = api_client.patch(
        set_permissions_url,
        [
            {
                "user": user_alice.get_absolute_url(response.wsgi_request),
                "permission": "no-access",
            }
        ],
    )
    assert response.status_code == 204  # Cannot remove permission from logged in user

    api_client.force_login(user_alice)
    response = api_client.get(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface.id))
    )
    assert response.status_code == 404


def test_set_surface_permissions_organization(
    api_client, user_alice, user_bob, org_blofield, handle_usage_statistics
):
    # We add both users to the Blofield organization
    org_blofield.add(user_alice)
    org_blofield.add(user_bob)

    # Create a surface and give Alice full access
    surface = SurfaceFactory(creator=user_alice)
    surface.grant_permission(user_alice, "full")

    # Bob cannot see this surface
    api_client.force_login(user_bob)
    response = api_client.get(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface.id))
    )
    assert response.status_code == 404

    # We now share with the Blofield organization
    api_client.force_login(user_alice)
    response = api_client.patch(
        reverse("manager:set-surface-permissions", kwargs=dict(pk=surface.id)),
        [
            {
                "organization": org_blofield.get_absolute_url(response.wsgi_request),
                "permission": "full",
            }
        ],
    )
    assert response.status_code == 204

    # Now Bob can see the surface because he is also in the Blofield organization
    api_client.force_login(user_bob)
    response = api_client.get(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface.id))
    )
    assert response.status_code == 200


def test_set_tag_permissions(api_client, user_alice, user_bob, handle_usage_statistics):
    surface1 = SurfaceFactory(creator=user_alice)
    surface2 = SurfaceFactory(creator=user_alice)
    surface1.grant_permission(user_alice, "full")
    surface2.grant_permission(user_alice, "edit")
    tag = TagFactory(surfaces=[surface1, surface2])

    api_client.force_login(user_bob)
    response = api_client.get(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface1.id))
    )
    assert response.status_code == 404
    response = api_client.get(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface2.id))
    )
    assert response.status_code == 404

    api_client.force_login(user_alice)
    response = api_client.patch(
        reverse("manager:set-tag-permissions", kwargs=dict(name=tag.name)),
        [
            {
                "user": user_bob.get_absolute_url(response.wsgi_request),
                "permission": "full",
            }
        ],
    )
    assert response.status_code == 200
    assert len(response.data["updated"]) == 1
    assert len(response.data["rejected"]) == 1

    api_client.force_login(user_bob)
    response = api_client.get(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface1.id))
    )
    assert response.status_code == 200
    response = api_client.get(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface2.id))
    )
    assert response.status_code == 404

    response = api_client.patch(
        reverse("manager:set-tag-permissions", kwargs=dict(name=tag.name)),
        [
            {
                "user": user_bob.get_absolute_url(response.wsgi_request),
                "permission": "no-access",
            }
        ],
    )
    assert response.status_code == 405  # Cannot remove permission from logged in user

    response = api_client.patch(
        reverse("manager:set-tag-permissions", kwargs=dict(name=tag.name)),
        [
            {
                "user": user_alice.get_absolute_url(response.wsgi_request),
                "permission": "no-access",
            }
        ],
    )
    assert response.status_code == 200  # Can remove permission from another user
    assert len(response.data["updated"]) == 1
    assert len(response.data["rejected"]) == 0

    api_client.force_login(user_alice)
    response = api_client.get(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface1.id))
    )
    assert response.status_code == 404

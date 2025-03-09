"""Test related to searching"""

import pytest
from django.conf import settings
from django.shortcuts import reverse
from django.test import override_settings
from rest_framework.test import APIRequestFactory

from topobank.manager.utils import subjects_to_base64
from topobank.manager.views import SurfaceViewSet
from topobank.testing.factories import SurfaceFactory, Topography1DFactory, UserFactory
from topobank.testing.utils import (
    ASSERT_EQUAL_IGNORE_VALUE,
    assert_dicts_equal,
    ordereddicts_to_dicts,
    search_surfaces,
)


@pytest.fixture
def user_three_surfaces_four_topographies():
    settings.DELETE_EXISTING_FILES = True
    #
    # Create some database objects
    #
    user = UserFactory()
    surface1 = SurfaceFactory(creator=user, category="exp")
    surface2 = SurfaceFactory(creator=user, category="sim")
    surface3 = SurfaceFactory(creator=user, category="dum")

    topo1a = Topography1DFactory(surface=surface1)
    topo1b = Topography1DFactory(surface=surface1)
    topo2a = Topography1DFactory(surface=surface2)
    topo2b = Topography1DFactory(surface=surface2)
    # no topography for surface3 on purpose

    return user, surface1, surface2, surface3, topo1a, topo1b, topo2a, topo2b


@override_settings(DELETE_EXISTING_FILES=True)
@pytest.mark.django_db
def test_surface_search_with_request_factory(user_three_surfaces_four_topographies):
    user, surface1, surface2, surface3, topo1a, topo1b, topo2a, topo2b = (
        user_three_surfaces_four_topographies
    )

    #
    # Set some tags
    #
    surface1.tags = ["bike", "train/tgv"]
    surface1.save()
    topo2a.tags = ["bike", "train/ice"]
    topo2a.save()

    #
    # Fix a selection and create a request with this selection
    #
    session = dict(
        selection=[
            f"surface-{surface2.pk}",
            f"topography-{topo1a.pk}",
            f"surface-{surface3.pk}",
        ]
    )

    factory = APIRequestFactory()
    request = factory.get(
        reverse("manager:surface-api-list")
    )  # no search term here, see below for another search with term
    request.user = user
    request.session = session

    #
    # Create search response and compare with expectation
    #
    response = SurfaceViewSet.as_view({"get": "list"})(request)

    assert response.status_code == 200

    user_url = user.get_absolute_url(request)

    topo1a_analyze = f"/ui/html/analysis-list/?subjects={subjects_to_base64([topo1a])}"
    topo1b_analyze = f"/ui/html/analysis-list/?subjects={subjects_to_base64([topo1b])}"
    topo2a_analyze = f"/ui/html/analysis-list/?subjects={subjects_to_base64([topo2a])}"
    topo2b_analyze = f"/ui/html/analysis-list/?subjects={subjects_to_base64([topo2b])}"
    surface1_analyze = (
        f"/ui/html/analysis-list/?subjects={subjects_to_base64([surface1])}"
    )
    surface2_analyze = (
        f"/ui/html/analysis-list/?subjects={subjects_to_base64([surface2])}"
    )

    expected_dicts = [
        {
            "category": "exp",
            "category_name": "Experimental data",
            "children": [
                {
                    "creator": user_url,
                    "creator_name": user.name,
                    "description": "",
                    "folder": False,
                    "key": f"topography-{topo1a.pk}",
                    "surface_key": f"surface-{surface1.pk}",
                    "label": topo1a.label,
                    "name": topo1a.name,
                    "id": topo1a.pk,
                    "publication_authors": None,
                    "publication_date": None,
                    "selected": True,
                    "sharing_status": "own",
                    "tags": [],
                    "title": topo1a.name,
                    "type": "topography",
                    "version": None,
                    "datafile_format": "xyz",
                    "height_scale": int(topo1a.height_scale),
                    "height_scale_editable": topo1a.height_scale_editable,
                    "instrument_name": "",
                    "instrument_parameters": {},
                    "instrument_type": "undefined",
                    "is_periodic": topo1a.is_periodic,
                    "measurement_date": str(topo1a.measurement_date),
                    "resolution_x": topo1a.resolution_x,
                    "resolution_y": topo1a.resolution_y,
                    "size_editable": topo1a.size_editable,
                    "size_x": topo1a.size_x,
                    "size_y": topo1a.size_y,
                    "thumbnail": ASSERT_EQUAL_IGNORE_VALUE,
                    "unit": topo1a.unit,
                    "unit_editable": topo1a.unit_editable,
                    "creation_datetime": topo1a.creation_datetime.astimezone().isoformat(),
                    "modification_datetime": topo1a.modification_datetime.astimezone().isoformat(),
                    "urls": {
                        "detail": f"/ui/html/topography/?topography={topo1a.id}",
                        "select": f"/ui/api/selection/topography/{topo1a.id}/select/",
                        "analyze": topo1a_analyze,
                        "unselect": f"/ui/api/selection/topography/{topo1a.id}/unselect/",
                    },
                },
                {
                    "creator": user_url,
                    "creator_name": user.name,
                    "description": "",
                    "folder": False,
                    "key": f"topography-{topo1b.pk}",
                    "surface_key": f"surface-{surface1.pk}",
                    "label": topo1b.label,
                    "name": topo1b.name,
                    "id": topo1b.pk,
                    "publication_authors": None,
                    "publication_date": None,
                    "selected": False,
                    "sharing_status": "own",
                    "tags": [],
                    "title": topo1b.name,
                    "type": "topography",
                    "version": None,
                    "datafile_format": "xyz",
                    "height_scale": topo1b.height_scale,
                    "height_scale_editable": topo1b.height_scale_editable,
                    "instrument_name": "",
                    "instrument_parameters": {},
                    "instrument_type": "undefined",
                    "is_periodic": topo1b.is_periodic,
                    "measurement_date": str(topo1b.measurement_date),
                    "resolution_x": topo1b.resolution_x,
                    "resolution_y": topo1b.resolution_y,
                    "size_editable": topo1b.size_editable,
                    "size_x": topo1b.size_x,
                    "size_y": topo1b.size_y,
                    "thumbnail": ASSERT_EQUAL_IGNORE_VALUE,
                    "unit": topo1b.unit,
                    "unit_editable": topo1b.unit_editable,
                    "creation_datetime": topo1b.creation_datetime.astimezone().isoformat(),
                    "modification_datetime": topo1b.modification_datetime.astimezone().isoformat(),
                    "urls": {
                        "detail": f"/ui/html/topography/?topography={topo1b.id}",
                        "select": f"/ui/api/selection/topography/{topo1b.id}/select/",
                        "analyze": topo1b_analyze,
                        "unselect": f"/ui/api/selection/topography/{topo1b.id}/unselect/",
                    },
                },
            ],
            "creator": user_url,
            "creator_name": user.name,
            "description": "",
            "folder": True,
            "key": f"surface-{surface1.pk}",
            "label": surface1.label,
            "name": surface1.name,
            "id": surface1.pk,
            "publication_authors": None,
            "publication_date": None,
            "publication_license": None,
            "publication_doi": None,
            "selected": False,
            "sharing_status": "own",
            "tags": ["bike", "train/tgv"],
            "title": surface1.name,
            "topography_count": 2,
            "type": "surface",
            "version": None,
            "creation_datetime": surface1.creation_datetime.astimezone().isoformat(),
            "modification_datetime": surface1.modification_datetime.astimezone().isoformat(),
            "urls": {
                "analyze": surface1_analyze,
                "download": f"/manager/api/surface/{surface1.id}/download/",
                "detail": f"/ui/html/dataset-detail/{surface1.id}/",
                "select": f"/ui/api/selection/surface/{surface1.id}/select/",
                "unselect": f"/ui/api/selection/surface/{surface1.id}/unselect/",
            },
        },
        {
            "category": "sim",
            "category_name": "Simulated data",
            "children": [
                {
                    "creator": user_url,
                    "creator_name": user.name,
                    "description": "",
                    "folder": False,
                    "key": f"topography-{topo2a.pk}",
                    "surface_key": f"surface-{surface2.pk}",
                    "label": topo2a.label,
                    "name": topo2a.name,
                    "id": topo2a.pk,
                    "publication_authors": None,
                    "publication_date": None,
                    "selected": False,  # not explicitly selected
                    "sharing_status": "own",
                    "tags": ["bike", "train/ice"],
                    "title": topo2a.name,
                    "type": "topography",
                    "version": None,
                    "datafile_format": "xyz",
                    "height_scale": topo2a.height_scale,
                    "height_scale_editable": topo2a.height_scale_editable,
                    "instrument_name": "",
                    "instrument_parameters": {},
                    "instrument_type": "undefined",
                    "is_periodic": topo2a.is_periodic,
                    "measurement_date": str(topo2a.measurement_date),
                    "resolution_x": topo2a.resolution_x,
                    "resolution_y": topo2a.resolution_y,
                    "size_editable": topo2a.size_editable,
                    "size_x": topo2a.size_x,
                    "size_y": topo2a.size_y,
                    "thumbnail": ASSERT_EQUAL_IGNORE_VALUE,
                    "unit": topo2a.unit,
                    "unit_editable": topo2a.unit_editable,
                    "creation_datetime": topo2a.creation_datetime.astimezone().isoformat(),
                    "modification_datetime": topo2a.modification_datetime.astimezone().isoformat(),
                    "urls": {
                        "detail": f"/ui/html/topography/?topography={topo2a.id}",
                        "select": f"/ui/api/selection/topography/{topo2a.id}/select/",
                        "analyze": topo2a_analyze,
                        "unselect": f"/ui/api/selection/topography/{topo2a.id}/unselect/",
                    },
                },
                {
                    "creator": user_url,
                    "creator_name": user.name,
                    "description": "",
                    "folder": False,
                    "key": f"topography-{topo2b.pk}",
                    "surface_key": f"surface-{surface2.pk}",
                    "label": topo2b.label,
                    "name": topo2b.name,
                    "id": topo2b.pk,
                    "publication_authors": None,
                    "publication_date": None,
                    "selected": False,  # not explicitly selected
                    "sharing_status": "own",
                    "tags": [],
                    "title": topo2b.name,
                    "type": "topography",
                    "version": None,
                    "datafile_format": "xyz",
                    "height_scale": topo2b.height_scale,
                    "height_scale_editable": topo2b.height_scale_editable,
                    "instrument_name": "",
                    "instrument_parameters": {},
                    "instrument_type": "undefined",
                    "is_periodic": topo2b.is_periodic,
                    "measurement_date": str(topo2b.measurement_date),
                    "resolution_x": topo2b.resolution_x,
                    "resolution_y": topo2b.resolution_y,
                    "size_editable": topo2b.size_editable,
                    "size_x": topo2b.size_x,
                    "size_y": topo2b.size_y,
                    "thumbnail": ASSERT_EQUAL_IGNORE_VALUE,
                    "unit": topo2b.unit,
                    "unit_editable": topo2b.unit_editable,
                    "creation_datetime": topo2b.creation_datetime.astimezone().isoformat(),
                    "modification_datetime": topo2b.modification_datetime.astimezone().isoformat(),
                    "urls": {
                        "detail": f"/ui/html/topography/?topography={topo2b.id}",
                        "select": f"/ui/api/selection/topography/{topo2b.id}/select/",
                        "analyze": topo2b_analyze,
                        "unselect": f"/ui/api/selection/topography/{topo2b.id}/unselect/",
                    },
                },
            ],
            "creator": user_url,
            "creator_name": user.name,
            "description": "",
            "folder": True,
            "key": f"surface-{surface2.pk}",
            "label": surface2.label,
            "name": surface2.name,
            "id": surface2.pk,
            "publication_authors": None,
            "publication_date": None,
            "publication_license": None,
            "publication_doi": None,
            "selected": True,
            "sharing_status": "own",
            "tags": [],
            "title": surface2.name,
            "topography_count": 2,
            "type": "surface",
            "version": None,
            "creation_datetime": surface2.creation_datetime.astimezone().isoformat(),
            "modification_datetime": surface2.modification_datetime.astimezone().isoformat(),
            "urls": {
                "analyze": surface2_analyze,
                "download": f"/manager/api/surface/{surface2.id}/download/",
                "detail": f"/ui/html/dataset-detail/{surface2.id}/",
                "select": f"/ui/api/selection/surface/{surface2.id}/select/",
                "unselect": f"/ui/api/selection/surface/{surface2.id}/unselect/",
            },
        },
        {
            "category": "dum",
            "category_name": "Dummy data",
            "children": [],
            "creator": user_url,
            "creator_name": user.name,
            "description": "",
            "folder": True,
            "key": f"surface-{surface3.pk}",
            "label": surface3.label,
            "name": surface3.name,
            "id": surface3.pk,
            "publication_authors": None,
            "publication_date": None,
            "publication_license": None,
            "publication_doi": None,
            "selected": True,
            "sharing_status": "own",
            "tags": [],
            "title": surface3.name,
            "topography_count": 0,
            "type": "surface",
            "version": None,
            "creation_datetime": surface3.creation_datetime.astimezone().isoformat(),
            "modification_datetime": surface3.modification_datetime.astimezone().isoformat(),
            "urls": {
                "download": f"/manager/api/surface/{surface3.id}/download/",
                "detail": f"/ui/html/dataset-detail/?surface={surface3.id}",
                "select": f"/ui/api/selection/surface/{surface3.id}/select/",
                "unselect": f"/ui/api/selection/surface/{surface3.id}/unselect/",
            },
        },
    ]

    assert_dicts_equal(
        ordereddicts_to_dicts(response.data["page_results"]), expected_dicts
    )

    #
    # Do a search and check for reduced results because search for "topo2a"
    #
    request = factory.get(reverse("ce_ui:search") + f"?search={topo2a.name}")
    request.user = user
    request.session = session

    #
    # Create search response and compare with expectation
    #
    response = SurfaceViewSet.as_view({"get": "list"})(request)

    assert response.status_code == 200

    expected_dicts = [
        {
            "category": "sim",
            "category_name": "Simulated data",
            "children": [
                {
                    "creator": user_url,
                    "creator_name": user.name,
                    "description": "",
                    "folder": False,
                    "key": f"topography-{topo2a.pk}",
                    "surface_key": f"surface-{surface2.pk}",
                    "label": topo2a.label,
                    "name": topo2a.name,
                    "id": topo2a.pk,
                    "publication_authors": None,
                    "publication_date": None,
                    "selected": False,  # not explicitly selected
                    "sharing_status": "own",
                    "tags": ["bike", "train/ice"],
                    "title": topo2a.name,
                    "type": "topography",
                    "version": None,
                    "datafile_format": "xyz",
                    "height_scale": int(topo2a.height_scale),
                    "height_scale_editable": topo2a.height_scale_editable,
                    "instrument_name": "",
                    "instrument_parameters": {},
                    "instrument_type": "undefined",
                    "is_periodic": topo2a.is_periodic,
                    "measurement_date": str(topo2a.measurement_date),
                    "resolution_x": topo2a.resolution_x,
                    "resolution_y": topo2a.resolution_y,
                    "size_editable": topo2a.size_editable,
                    "size_x": topo2a.size_x,
                    "size_y": topo2a.size_y,
                    "thumbnail": ASSERT_EQUAL_IGNORE_VALUE,
                    "unit": topo2a.unit,
                    "unit_editable": topo2a.unit_editable,
                    "creation_datetime": topo2a.creation_datetime.astimezone().isoformat(),
                    "modification_datetime": topo2a.modification_datetime.astimezone().isoformat(),
                    "urls": {
                        "detail": f"/ui/html/topography/?topography={topo2a.id}",
                        "select": f"/ui/api/selection/topography/{topo2a.id}/select/",
                        "analyze": topo2a_analyze,
                        "unselect": f"/ui/api/selection/topography/{topo2a.id}/unselect/",
                    },
                },
            ],
            "creator": user_url,
            "creator_name": user.name,
            "description": "",
            "folder": True,
            "key": f"surface-{surface2.pk}",
            "label": surface2.label,
            "name": surface2.name,
            "id": surface2.pk,
            "publication_authors": None,
            "publication_date": None,
            "publication_license": None,
            "publication_doi": None,
            "selected": True,
            "sharing_status": "own",
            "tags": [],
            "title": surface2.name,
            "topography_count": 2,
            "type": "surface",
            "version": None,
            "creation_datetime": surface2.creation_datetime.astimezone().isoformat(),
            "modification_datetime": surface2.modification_datetime.astimezone().isoformat(),
            "urls": {
                "analyze": surface2_analyze,
                "download": f"/manager/api/surface/{surface2.id}/download/",
                "detail": f"/ui/html/dataset-detail/?surface={surface2.id}",
                "select": f"/ui/api/selection/surface/{surface2.id}/select/",
                "unselect": f"/ui/api/selection/surface/{surface2.id}/unselect/",
            },
        },
    ]

    resulted_dicts = ordereddicts_to_dicts(
        response.data["page_results"], sorted_by="title"
    )
    assert_dicts_equal(resulted_dicts, expected_dicts)


@override_settings(DELETE_EXISTING_FILES=True)
@pytest.mark.django_db
def test_search_expressions_with_request_factory():
    user = UserFactory()

    surface1 = SurfaceFactory(creator=user)

    topo1a = Topography1DFactory(surface=surface1, description="a big tiger")
    topo1b = Topography1DFactory(surface=surface1, description="a big elephant")
    topo1c = Topography1DFactory(
        surface=surface1, description="Find this here and a small ant"
    )
    topo1d = Topography1DFactory(surface=surface1, description="not me, big snake")

    surface2 = SurfaceFactory(creator=user)

    topo2a = Topography1DFactory(surface=surface2, name="Measurement 2A")
    Topography1DFactory(
        surface=surface2, name="Measurement 2B", description="a small lion"
    )

    #
    # Set some tags
    #
    topo1b.tags = ["bike"]
    topo1b.save()
    topo1c.tags = ["transport/bike"]
    topo1c.save()
    topo1d.tags = ["bike"]
    topo1d.save()

    #
    # Define helper function for testing searching
    #
    factory = APIRequestFactory()

    # simple search for a topography by name given a phrase
    result = search_surfaces(factory, user, f"'{topo2a.name}'")
    assert len(result) == 1  # one surface
    assert len(result[0]["children"]) == 1  # one topography
    assert result[0]["children"][0]["name"] == topo2a.name

    # AND search for topographies by name
    result = search_surfaces(factory, user, f'"{topo2a.name}" "{topo1a.name}"')
    assert len(result) == 0  # no surfaces

    # OR search for topographies by name
    result = search_surfaces(factory, user, f'"{topo2a.name}" OR "{topo1a.name}"')
    assert len(result) == 2  # two surfaces
    # noinspection DuplicatedCode
    assert len(result[0]["children"]) == 1  # one topography
    assert len(result[1]["children"]) == 1  # one topography
    assert result[0]["children"][0]["name"] == topo1a.name
    assert result[1]["children"][0]["name"] == topo2a.name

    # Exclusion using '-'
    result = search_surfaces(factory, user, "-elephant")
    assert len(result) == 2
    assert result[0]["name"] == surface1.name
    assert result[1]["name"] == surface2.name
    assert len(result[0]["children"]) == 3  # here one measurement is excluded
    assert len(result[1]["children"]) == 2

    # Searching nearby
    result = search_surfaces(factory, user, "Find * here")
    assert len(result) == 1
    assert result[0]["name"] == surface1.name
    assert len(result[0]["children"]) == 1  # here one measurement has it
    assert result[0]["children"][0]["description"] == "Find this here and a small ant"

    # more complex search expression using a phrase
    #
    # Parentheses do not work with 'websearch' for simplicity.
    #
    # (NOT) binds most tightly, "quoted text" (FOLLOWED BY) next most tightly,
    # then AND (default if no parameter), with OR binding the least tightly.
    #

    # result = search_surfaces(f'bike AND "a big" or "a small" -"not me"')
    result = search_surfaces(factory, user, "bike -snake big")

    assert len(result) == 1  # surface 2 is excluded because there is no "bike"
    assert result[0]["name"] == surface1.name
    assert len(result[0]["children"]) == 1
    assert (
        result[0]["children"][0]["name"] == topo1b.name
    )  # topo1d is excluded because of 'not me'


@override_settings(DELETE_EXISTING_FILES=True)
@pytest.mark.django_db
def test_search_for_user_with_request_factory():
    user1 = UserFactory(name="Bob Marley")
    user2 = UserFactory(name="Bob Dylan")

    surf1 = SurfaceFactory(creator=user1)
    surf2 = SurfaceFactory(creator=user2)

    request_factory = APIRequestFactory()

    #
    # So far nothing has been shared
    #
    # User 1 searches
    result = search_surfaces(request_factory, user1, "Bob")
    assert len(result) == 1
    assert result[0]["name"] == surf1.name
    assert len(result[0]["children"]) == 0

    result = search_surfaces(request_factory, user1, "Marley")
    assert len(result) == 1
    assert result[0]["name"] == surf1.name
    assert len(result[0]["children"]) == 0

    result = search_surfaces(request_factory, user1, "Dylan")
    assert len(result) == 0

    # User 2 searches
    result = search_surfaces(request_factory, user2, "Bob")
    assert len(result) == 1
    assert result[0]["name"] == surf2.name
    assert len(result[0]["children"]) == 0

    result = search_surfaces(request_factory, user2, "Marley")
    assert len(result) == 0

    result = search_surfaces(request_factory, user2, "Dylan")
    assert len(result) == 1
    assert result[0]["name"] == surf2.name
    assert len(result[0]["children"]) == 0

    #
    # User1 shares his surface with user2
    #
    surf1.grant_permission(user2, "edit")

    # User 2 searches, now surface of user 1 is also visible
    result = search_surfaces(request_factory, user2, "Bob")
    assert len(result) == 2
    assert set(r["name"] for r in result) == set((surf1.name, surf2.name))
    assert len(result[0]["children"]) == 0
    assert len(result[1]["children"]) == 0

    result = search_surfaces(request_factory, user2, "Marley")
    assert len(result) == 1
    assert result[0]["name"] == surf1.name
    assert len(result[0]["children"]) == 0

    result = search_surfaces(request_factory, user2, "Dylan")
    assert len(result) == 1
    assert result[0]["name"] == surf2.name
    assert len(result[0]["children"]) == 0

    #
    # User1 adds a topography to shared surface, it should be findable by both users using first user's name
    #
    topo1a = Topography1DFactory(surface=surf1, creator=user1)

    # User 1 searches, finds also topography
    result = search_surfaces(request_factory, user1, "Bob")
    assert len(result) == 1
    assert result[0]["name"] == surf1.name
    assert len(result[0]["children"]) == 1

    result = search_surfaces(request_factory, user1, "Marley")
    assert len(result) == 1
    assert result[0]["name"] == surf1.name
    assert len(result[0]["children"]) == 1

    result = search_surfaces(request_factory, user1, "Dylan")
    assert len(result) == 0

    # User 2 searches, finds also topography of user 1 in shared surface
    result = search_surfaces(request_factory, user2, "Bob")
    assert len(result) == 2
    assert set(r["name"] for r in result) == set((surf1.name, surf2.name))
    assert len(result[0]["children"]) == 1
    assert len(result[1]["children"]) == 0  # user2's own surface has no topography

    result = search_surfaces(request_factory, user2, "Marley")
    assert len(result) == 1
    assert result[0]["name"] == surf1.name
    assert len(result[0]["children"]) == 1

    result = search_surfaces(request_factory, user2, "Dylan")
    assert len(result) == 1
    assert result[0]["name"] == surf2.name
    assert len(result[0]["children"]) == 0

    #
    # User2 adds a topography to shared surface, it should be findable by both users using user2's last name
    #
    topo1b = Topography1DFactory(surface=surf1, creator=user2)

    # User 1 searches, finds topographies, depending on search term
    result = search_surfaces(request_factory, user1, "Bob")
    assert len(result) == 1
    assert result[0]["name"] == surf1.name
    assert len(result[0]["children"]) == 2

    result = search_surfaces(request_factory, user1, "Marley")
    assert len(result) == 1
    assert result[0]["name"] == surf1.name
    assert (
        len(result[0]["children"]) == 1
    )  # topography uploaded by user2 should not be shown
    assert result[0]["children"][0]["name"] == topo1a.name

    result = search_surfaces(request_factory, user1, "Dylan")
    assert len(result) == 1
    assert (
        result[0]["name"] == surf1.name
    )  # now own surface is also listed with one topography matching "Dylan"
    assert (
        len(result[0]["children"]) == 1
    )  # topography uploaded by user2 should be shown alone
    assert result[0]["children"][0]["name"] == topo1b.name

    # User 2 searches, finds also topography of user 1 in shared surface
    result = search_surfaces(request_factory, user2, "Bob")
    assert len(result) == 2
    assert set(r["name"] for r in result) == set((surf1.name, surf2.name))
    assert len(result[0]["children"]) == 2
    assert len(result[1]["children"]) == 0  # user2's own surface has no topography

    result = search_surfaces(request_factory, user2, "Marley")
    assert len(result) == 1
    assert result[0]["name"] == surf1.name
    assert (
        len(result[0]["children"]) == 1
    )  # topography uploaded by user1 should be shown alone
    assert result[0]["children"][0]["name"] == topo1a.name

    result = search_surfaces(request_factory, user2, "Dylan")
    assert len(result) == 2
    assert set(r["name"] for r in result) == set(
        (surf1.name, surf2.name)
    )  # now also surf1 is listed
    assert result[0]["name"] == surf1.name
    assert (
        len(result[0]["children"]) == 1
    )  # topography uploaded by user1 should be shown alone
    assert result[0]["children"][0]["name"] == topo1b.name
    assert result[1]["name"] == surf2.name
    assert len(result[1]["children"]) == 0

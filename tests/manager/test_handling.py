import datetime
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.storage import default_storage
from django.shortcuts import reverse
from django.utils.text import slugify
from pytest import approx

from topobank.authorization.models import PermissionSet
from topobank.files.models import Folder, Manifest
from topobank.manager.models import MAX_LENGTH_DATAFILE_FORMAT, Surface, Topography
from topobank.testing.factories import (
    FIXTURE_DATA_DIR,
    SurfaceFactory,
    TagFactory,
    Topography1DFactory,
    Topography2DFactory,
    UserFactory,
)
from topobank.testing.utils import upload_topography_file

filelist = [
    "10x10.txt",
    "example.opd",
    "example3.di",
    "plux-1.plux",  # has undefined data
    "dektak-1.csv",  # nonuniform line scan
]


#######################################################################
# Topographies
#######################################################################


#
# Different formats are handled by SurfaceTopography
# and should be tested there in general, but
# we add some supplib for formats which had problems because
# of the topobank code
#
@pytest.mark.django_db
def test_upload_topography_di(
    api_client, handle_usage_statistics, django_capture_on_commit_callbacks
):
    name = "example3.di"
    input_file_path = Path(
        f"{FIXTURE_DATA_DIR}/{name}"
    )  # maybe use package 'pytest-datafiles' here instead
    description = "test description"
    category = "exp"

    user = UserFactory()

    api_client.force_login(user)

    # first create a surface
    response = api_client.post(reverse("manager:surface-api-list"))
    assert response.status_code == 201, response.content  # Created
    surface_id = response.data["id"]

    # populate surface with some info
    response = api_client.patch(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface_id)),
        {"name": "surface1", "category": category, "description": description},
    )
    assert response.status_code == 200, response.content

    response = upload_topography_file(
        str(input_file_path), surface_id, api_client, django_capture_on_commit_callbacks
    )

    # we should have four datasources as options
    assert response.data["name"] == "example3.di"
    assert response.data["channel_names"] == [
        ["ZSensor", "nm"],
        ["AmplitudeError", None],
        ["Phase", None],
        ["Height", "nm"],
    ]

    # Update metadata
    topography_id = response.data["id"]
    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topography_id)),
        {
            "measurement_date": "2018-06-21",
            "data_source": 0,
            "description": description,
        },
    )
    assert response.status_code == 200, response.content
    assert response.data["measurement_date"] == "2018-06-21"
    assert response.data["description"] == description

    # Update more metadata
    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topography_id)),
        {
            "size_x": "9000",
            "size_y": "9000",
            "unit": "nm",
            "height_scale": 0.3,
            "detrend_mode": "height",
            "resolution_x": 256,
            "resolution_y": 256,
            "instrument_type": Topography.INSTRUMENT_TYPE_UNDEFINED,
            "fill_undefined_data_mode": Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING,
        },
    )
    assert response.status_code == 400, response.content

    # Check that updating fixed metadata leads to an error
    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topography_id)),
        {
            "size_x": "1.0",
        },
    )
    assert response.status_code == 400, response.content

    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topography_id)),
        {
            "unit": "m",
            "height_scale": 1.3,
        },
    )
    assert response.status_code == 400, response.content

    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topography_id)),
        {
            "resolution_x": 300,
        },
    )
    assert response.status_code == 400, response.content  # resolution_x is read only

    surface = Surface.objects.get(name="surface1")
    topos = surface.topography_set.all()

    assert len(topos) == 1

    t = topos[0]

    assert t.measurement_date == datetime.date(2018, 6, 21)
    assert t.description == description
    assert "example3" in t.datafile.filename
    assert 256 == t.resolution_x
    assert 256 == t.resolution_y
    assert t.creator == user
    assert t.datafile_format == "di"


@pytest.mark.skip(
    reason="Fails in CI with: PostgreSQL text fields cannot contain NUL (0x00) bytes"
)
@pytest.mark.django_db
def test_upload_topography_npy(
    api_client, settings, handle_usage_statistics, django_capture_on_commit_callbacks
):
    settings.CELERY_TASK_ALWAYS_EAGER = True  # perform tasks locally

    user = UserFactory()
    surface = SurfaceFactory(creator=user, name="surface1")
    description = "Some description"
    api_client.force_login(user)

    # upload file
    name = "example-2d.npy"
    input_file_path = Path(
        f"{FIXTURE_DATA_DIR}/{name}"
    )  # maybe use package 'pytest-datafiles' here instead
    response = upload_topography_file(
        str(input_file_path), surface.id, api_client, django_capture_on_commit_callbacks
    )

    # idiot-check some response properties
    assert response.data["name"] == "example-2d.npy"

    # Updated metadata
    topography_id = response.data["id"]
    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topography_id)),
        {
            "measurement_date": "2020-10-21",
            "data_source": 0,
            "description": description,
        },
    )
    assert response.status_code == 200, response.content
    assert response.data["measurement_date"] == "2020-10-21"
    assert response.data["description"] == description

    # Update more metadata
    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topography_id)),
        {
            "size_x": "1",
            "size_y": "1",
            "unit": "nm",
            "height_scale": 1,
            "detrend_mode": "height",
            "resolution_x": 2,
            "resolution_y": 2,
            "instrument_type": Topography.INSTRUMENT_TYPE_UNDEFINED,
            "fill_undefined_data_mode": Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING,
        },
    )
    assert (
        response.status_code == 400
    ), response.content  # resolution_x and resolution_y are read only

    # Update more metadata
    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topography_id)),
        {
            "size_x": "1",
            "size_y": "1",
            "unit": "nm",
            "height_scale": 1,
            "detrend_mode": "height",
            "instrument_type": Topography.INSTRUMENT_TYPE_UNDEFINED,
            "fill_undefined_data_mode": Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING,
        },
    )
    assert (
        response.status_code == 200
    ), response.content  # without resolution_x and resolution_y

    surface = Surface.objects.get(name="surface1")
    topos = surface.topography_set.all()

    assert len(topos) == 1

    t = topos[0]

    assert t.measurement_date == datetime.date(2020, 10, 21)
    assert t.description == description
    assert "example-2d" in t.datafile.filename
    assert 2 == t.resolution_x
    assert 2 == t.resolution_y
    assert t.creator == user
    assert t.datafile_format == "npy"


@pytest.mark.parametrize(
    (
        "input_filename",
        "exp_datafile_format",
        "exp_resolution_x",
        "exp_resolution_y",
        "physical_sizes_to_be_set",
        "exp_physical_sizes",
    ),
    [
        (FIXTURE_DATA_DIR + "/10x10.txt", "asc", 10, 10, (1, 1), (1, 1)),
        (FIXTURE_DATA_DIR + "/line_scan_1.asc", "xyz", 11, None, None, (9.0,)),
        (
            FIXTURE_DATA_DIR + "/line_scan_1_minimal_spaces.asc",
            "xyz",
            11,
            None,
            None,
            (9.0,),
        ),
        (FIXTURE_DATA_DIR + "/example6.txt", "asc", 9, None, (1.0,), (1.0,)),
    ],
)
# Add this for a larger file: ("topobank/manager/fixtures/500x500_random.txt", 500)]) # takes quire long
@pytest.mark.django_db
def test_upload_topography_txt(
    api_client,
    django_user_model,
    django_capture_on_commit_callbacks,
    input_filename,
    exp_datafile_format,
    exp_resolution_x,
    exp_resolution_y,
    physical_sizes_to_be_set,
    exp_physical_sizes,
    handle_usage_statistics,
):
    settings.CELERY_TASK_ALWAYS_EAGER = True  # perform tasks locally

    input_file_path = Path(input_filename)
    expected_toponame = input_file_path.name

    description = "test description"

    username = "testuser"
    password = "abcd$1234"

    django_user_model.objects.create_user(username=username, password=password)

    assert api_client.login(username=username, password=password)

    # first create a surface
    response = api_client.post(
        reverse("manager:surface-api-list"),
        data={"name": "surface1", "category": "sim"},
    )
    assert response.status_code == 201, response.content

    # populate surface with some info
    surface_id = response.data["id"]
    response = api_client.patch(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface_id)),
        {"category": "exp", "description": description},
    )
    assert response.status_code == 200, response.content

    response = upload_topography_file(
        str(input_file_path), surface_id, api_client, django_capture_on_commit_callbacks
    )
    assert response.data["name"] == expected_toponame

    # Updated metadata
    topography_id = response.data["id"]
    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topography_id)),
        {
            "measurement_date": "2018-06-21",
            "data_source": 0,
            "description": description,
        },
    )
    assert response.status_code == 200, response.content
    assert response.data["measurement_date"] == "2018-06-21"
    assert response.data["description"] == description

    # Update more metadata
    if exp_resolution_y is None:
        data = {}
        if physical_sizes_to_be_set is not None:
            data["size_x"] = physical_sizes_to_be_set[0]
        response = api_client.patch(
            reverse("manager:topography-api-detail", kwargs=dict(pk=topography_id)),
            {
                **data,
                "unit": "nm",
                "height_scale": 1,
                "detrend_mode": "height",
                "instrument_type": Topography.INSTRUMENT_TYPE_UNDEFINED,
                "fill_undefined_data_mode": Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING,
            },
        )
    else:
        data = {}
        if physical_sizes_to_be_set is not None:
            data["size_x"] = physical_sizes_to_be_set[0]
            data["size_y"] = physical_sizes_to_be_set[1]
        response = api_client.patch(
            reverse("manager:topography-api-detail", kwargs=dict(pk=topography_id)),
            {
                **data,
                "unit": "nm",
                "height_scale": 1,
                "detrend_mode": "height",
                "instrument_type": Topography.INSTRUMENT_TYPE_UNDEFINED,
                "fill_undefined_data_mode": Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING,
            },
        )
    assert response.status_code == 200, response.content

    surface = Surface.objects.get(name="surface1")
    topos = surface.topography_set.all()

    assert len(topos) == 1

    t = topos[0]

    assert t.measurement_date == datetime.date(2018, 6, 21)
    assert t.description == description
    assert input_file_path.stem in t.datafile.filename
    assert exp_resolution_x == t.resolution_x
    assert exp_resolution_y == t.resolution_y
    assert t.datafile_format == exp_datafile_format
    assert t.instrument_type == Topography.INSTRUMENT_TYPE_UNDEFINED
    assert t.instrument_parameters == {}

    #
    # Also check some properties of the SurfaceTopography.Topography
    #
    st_topo = t.topography(allow_squeezed=False)
    assert st_topo.physical_sizes == exp_physical_sizes


@pytest.mark.parametrize("input_filename", filelist)
@pytest.mark.parametrize(
    "instrument_type,resolution_value,resolution_unit,tip_radius_value,tip_radius_unit,response_code",
    [
        (
            Topography.INSTRUMENT_TYPE_UNDEFINED,
            "",
            "",
            "",
            "",
            200,
        ),  # empty instrument params
        (
            Topography.INSTRUMENT_TYPE_UNDEFINED,
            10.0,
            "km",
            2.0,
            "nm",
            200,
        ),  # also empty params
        (Topography.INSTRUMENT_TYPE_MICROSCOPE_BASED, 10.0, "nm", "", "", 200),
        (
            Topography.INSTRUMENT_TYPE_MICROSCOPE_BASED,
            "",
            "nm",
            "",
            "",
            400,  # value missing
        ),  # no value! -> also empty
        (Topography.INSTRUMENT_TYPE_CONTACT_BASED, "", "", 1.0, "mm", 200),
        (
            Topography.INSTRUMENT_TYPE_CONTACT_BASED,
            "",
            "",
            "",
            "mm",
            400,  # value missing
        ),  # no value! -> also empty
    ],
)
@pytest.mark.django_db
def test_upload_topography_instrument_parameters(
    api_client,
    settings,
    django_capture_on_commit_callbacks,
    django_user_model,
    input_filename,
    instrument_type,
    resolution_value,
    resolution_unit,
    tip_radius_value,
    tip_radius_unit,
    response_code,
    handle_usage_statistics,
):
    settings.CELERY_TASK_ALWAYS_EAGER = True

    input_file_path = Path(f"{FIXTURE_DATA_DIR}/{input_filename}")
    expected_toponame = input_file_path.name

    description = "test description"

    username = "testuser"
    password = "abcd$1234"

    instrument_name = "My Profilometer"

    django_user_model.objects.create_user(username=username, password=password)

    assert api_client.login(username=username, password=password)

    # first create a surface
    response = api_client.post(
        reverse("manager:surface-api-list"), {"name": "surface1", "category": "sim"}
    )
    assert response.status_code == 201

    surface = Surface.objects.get(name="surface1")

    response = upload_topography_file(
        str(input_file_path), surface.id, api_client, django_capture_on_commit_callbacks
    )
    assert response.data["name"] == expected_toponame

    # create parameters dictionary
    instrument_parameters = {}
    if instrument_type == Topography.INSTRUMENT_TYPE_MICROSCOPE_BASED:
        instrument_parameters["resolution"] = {
            "value": resolution_value,
            "unit": resolution_unit,
        }
    elif instrument_type == Topography.INSTRUMENT_TYPE_CONTACT_BASED:
        instrument_parameters["tip_radius"] = {
            "value": tip_radius_value,
            "unit": tip_radius_unit,
        }

    # Metadata dictionary
    data = {
        "name": "topo1",
        "measurement_date": "2018-06-21",
        "data_source": 0,
        "description": description,
        "detrend_mode": "height",
        "instrument_name": instrument_name,
        "instrument_type": instrument_type,
        "instrument_parameters": instrument_parameters,
        "fill_undefined_data_mode": Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING,
    }

    if response.data["size_editable"]:
        data["size_x"] = 1
        data["size_y"] = 1
    if response.data["unit_editable"]:
        data["unit"] = "nm"
    if response.data["height_scale_editable"]:
        data["height_scale"] = 1

    # Update metadata
    id = response.data["id"]
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.patch(
            reverse("manager:topography-api-detail", kwargs=dict(pk=id)),
            data,
        )
        assert response.status_code == response_code, response.content
        if response_code == 400:
            # Try again, but without instrument parameters
            del data["instrument_parameters"]
            response = api_client.patch(
                reverse("manager:topography-api-detail", kwargs=dict(pk=id)),
                data,
            )
            assert response.status_code == 200, response.content
        assert response.data["task_state"] == "pe"  # This is always pending

    # Get metadata
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.get(
            reverse("manager:topography-api-detail", kwargs=dict(pk=id))
        )
        assert response.status_code == 200, response.message
        assert response.data["task_state"] == "su"  # This should be a success

    surface = Surface.objects.get(name="surface1")
    topos = surface.topography_set.all()

    assert len(topos) == 1

    t = topos[0]

    assert t.measurement_date == datetime.date(2018, 6, 21)
    assert t.description == description
    assert input_file_path.stem in t.datafile.filename
    assert t.instrument_type == instrument_type
    if response_code == 200:
        expected_instrument_parameters = {}
        clean_instrument_parameters = {}
        if instrument_type == Topography.INSTRUMENT_TYPE_MICROSCOPE_BASED:
            expected_instrument_parameters = {
                "resolution": {"unit": resolution_unit, "value": resolution_value}
            }
            if resolution_value != "":
                clean_instrument_parameters = expected_instrument_parameters
        elif instrument_type == Topography.INSTRUMENT_TYPE_CONTACT_BASED:
            expected_instrument_parameters = {
                "tip_radius": {"unit": tip_radius_unit, "value": tip_radius_value}
            }
            if tip_radius_value != "":
                clean_instrument_parameters = expected_instrument_parameters

        assert t.instrument_parameters == expected_instrument_parameters

        #
        # Also check some properties of the SurfaceTopography.Topography
        #
        st_topo = t.topography(allow_squeezed=False)
        assert st_topo.info["instrument"] == {
            "name": instrument_name,
            "parameters": clean_instrument_parameters,
        }
        if "parameters" in t.instrument_info["instrument"]:
            assert (
                t.instrument_info["instrument"]["parameters"]
                == clean_instrument_parameters
            )
        else:
            assert clean_instrument_parameters == {}


@pytest.mark.parametrize(
    "input_filename", [f for f in filelist if not f.endswith(".plux")]
)
@pytest.mark.parametrize(
    "fill_undefined_data_mode",
    [
        Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING,
        Topography.FILL_UNDEFINED_DATA_MODE_HARMONIC,
    ],
)
@pytest.mark.django_db
def test_upload_topography_fill_undefined_data(
    api_client,
    settings,
    django_capture_on_commit_callbacks,
    django_user_model,
    input_filename,
    fill_undefined_data_mode,
    handle_usage_statistics,
):
    settings.CELERY_TASK_ALWAYS_EAGER = True

    input_file_path = Path(f"{FIXTURE_DATA_DIR}/{input_filename}")
    expected_toponame = input_file_path.name

    description = "test description"

    username = "testuser"
    password = "abcd$1234"

    django_user_model.objects.create_user(username=username, password=password)

    assert api_client.login(username=username, password=password)

    # first create a surface
    response = api_client.post(
        reverse("manager:surface-api-list"), {"name": "surface1", "category": "sim"}
    )
    assert response.status_code == 201

    surface = Surface.objects.get(name="surface1")

    response = upload_topography_file(
        str(input_file_path), surface.id, api_client, django_capture_on_commit_callbacks
    )
    assert response.data["name"] == expected_toponame

    # Update metadata
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.patch(
            reverse(
                "manager:topography-api-detail", kwargs=dict(pk=response.data["id"])
            ),
            {
                "description": description,
                "fill_undefined_data_mode": fill_undefined_data_mode,
            },
        )
        assert response.status_code == 200, response.content
        assert response.data["task_state"] in ["su", "pe"]

    surface = Surface.objects.get(name="surface1")
    topos = surface.topography_set.all()

    assert len(topos) == 1

    t = topos[0]

    assert t.description == description
    assert t.fill_undefined_data_mode == fill_undefined_data_mode
    assert t.task_state == "su"
    assert t.task_memory > 10  # should be more than some small number


@pytest.mark.django_db
def test_upload_topography_and_name_like_an_existing_for_same_surface(
    api_client, settings, django_capture_on_commit_callbacks
):
    settings.CELERY_TASK_ALWAYS_EAGER = True

    input_file_path = Path(FIXTURE_DATA_DIR + "/10x10.txt")

    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    Topography1DFactory(
        surface=surface, name="TOPO"
    )  # <-- we will try to create another topography named TOPO later

    api_client.force_login(user)

    response = upload_topography_file(
        str(input_file_path),
        surface.id,
        api_client,
        django_capture_on_commit_callbacks,
        measurement_date="2018-06-21",
        data_source=0,
        description="bla",
    )

    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=response.data["id"])),
        {"name": "TOPO"},
    )
    assert (
        response.status_code == 400
    ), response.content  # There can only be one topography with the same name

    # topo2 = Topography.objects.get(pk=response.data['id'])
    # Both can have same name
    # assert topo1.name == 'TOPO'
    # assert topo2.name == 'TOPO'


@pytest.mark.django_db
def test_trying_upload_of_topography_file_with_unknown_format(
    api_client,
    settings,
    django_capture_on_commit_callbacks,
    django_user_model,
    handle_usage_statistics,
):
    settings.CELERY_TASK_ALWAYS_EAGER = True

    input_file_path = Path(f"{FIXTURE_DATA_DIR}/dummy.txt")  # this is nonsense

    username = "testuser"
    password = "abcd$1234"

    django_user_model.objects.create_user(username=username, password=password)

    assert api_client.login(username=username, password=password)

    # first create a surface
    response = api_client.post(
        reverse("manager:surface-api-list"),
        data={
            "name": "surface1",
            "category": "dum",
        },
    )
    assert response.status_code == 201, response.content

    surface = Surface.objects.get(name="surface1")

    # upload file
    response = upload_topography_file(
        str(input_file_path),
        surface.id,
        api_client,
        django_capture_on_commit_callbacks,
        final_task_state="fa",
    )
    assert (
        response.data["task_error"]
        == "The data file is of an unknown or unsupported format."
    )


@pytest.mark.skip(
    "Skip test, this is not handled gracefully by the current implementation"
)
@pytest.mark.django_db
def test_trying_upload_of_topography_file_with_too_long_format_name(
    api_client,
    settings,
    django_capture_on_commit_callbacks,
    django_user_model,
    mocker,
    handle_usage_statistics,
):
    settings.CELERY_TASK_ALWAYS_EAGER = True

    import SurfaceTopography.IO

    too_long_datafile_format = "a" * (MAX_LENGTH_DATAFILE_FORMAT + 1)

    m = mocker.patch("SurfaceTopography.IO.DIReader.format")
    m.return_value = too_long_datafile_format
    # this special detect_format function returns a format which is too long
    # this should result in an error message
    assert SurfaceTopography.IO.DIReader.format() == too_long_datafile_format

    input_file_path = Path(FIXTURE_DATA_DIR + "/example3.di")

    user = UserFactory()

    api_client.force_login(user)

    surface = SurfaceFactory(creator=user)

    response = upload_topography_file(
        str(input_file_path), surface.id, api_client, django_capture_on_commit_callbacks
    )
    assert response.status_code == 200, response.content


@pytest.mark.django_db
def test_trying_upload_of_corrupted_topography_file(
    api_client, settings, django_capture_on_commit_callbacks, django_user_model
):
    settings.CELERY_TASK_ALWAYS_EAGER = True

    input_file_path = Path(FIXTURE_DATA_DIR + "/example3_corrupt.di")
    # I used the correct file "example3.di" and broke it on purpose
    # The headers are still okay, but the topography can't be read by PyCo
    # using .topography() and leads to a "ValueError: buffer is smaller
    # than requested size"

    category = "exp"

    username = "testuser"
    password = "abcd$1234"

    django_user_model.objects.create_user(username=username, password=password)

    assert api_client.login(username=username, password=password)

    # first create a surface
    response = api_client.post(
        reverse("manager:surface-api-list"),
        {
            "name": "surface1",
            "category": category,
        },
    )
    assert response.status_code == 201, response.content

    surface = Surface.objects.get(name="surface1")

    # file upload
    response = upload_topography_file(
        str(input_file_path),
        surface.id,
        api_client,
        django_capture_on_commit_callbacks,
        final_task_state="fa",
    )

    # This should yield an error
    assert (
        response.data["task_error"]
        == "The data file is of an unknown or unsupported format."
    )

    #
    # Topography has been saved, but with state failed
    #
    surface = Surface.objects.get(name="surface1")
    topos = surface.topography_set.all()

    assert len(topos) == 1
    assert topos[0].task_state == "fa"
    assert (
        topos[0].task_error == "The data file is of an unknown or unsupported format."
    )


@pytest.mark.django_db
def test_upload_opd_file_check(
    api_client, settings, django_capture_on_commit_callbacks, handle_usage_statistics
):
    settings.CELERY_TASK_ALWAYS_EAGER = True

    user = UserFactory()
    surface = SurfaceFactory(creator=user, name="surface1")
    description = "Some description"
    api_client.force_login(user)

    # file upload
    input_file_path = Path(
        FIXTURE_DATA_DIR + "/example.opd"
    )  # maybe use package 'pytest-datafiles' here instead
    response = upload_topography_file(
        str(input_file_path),
        surface.id,
        api_client,
        django_capture_on_commit_callbacks,
        measurement_date="2021-06-09",
        description=description,
        detrend_mode="height",
    )

    assert response.data["channel_names"] == [["Raw", "mm"]]
    assert response.data["name"] == "example.opd"

    # check whether known values for size and height scale are in content
    assert response.data["size_x"] == approx(0.1485370245)
    assert response.data["size_y"] == approx(0.1500298589)
    assert response.data["height_scale"] == approx(0.0005343980102539062)

    surface = Surface.objects.get(name="surface1")
    topos = surface.topography_set.all()

    assert len(topos) == 1

    t = topos[0]

    assert t.measurement_date == datetime.date(2021, 6, 9)
    assert t.description == description
    assert "example" in t.datafile.filename
    assert t.size_x == approx(0.1485370245)
    assert t.size_y == approx(0.1500298589)
    assert t.resolution_x == approx(199)
    assert t.resolution_y == approx(201)
    assert t.height_scale == approx(0.0005343980102539062)
    assert t.creator == user
    assert t.datafile_format == "opd"
    assert not t.size_editable
    assert not t.height_scale_editable
    assert not t.unit_editable


@pytest.mark.django_db
def test_topography_list(
    api_client, two_topos, django_user_model, handle_usage_statistics
):
    username = "testuser"
    password = "abcd$1234"

    assert api_client.login(username=username, password=password)

    # response = client.get(reverse('manager:surface-detail', kwargs=dict(pk=1)))

    #
    # all topographies for 'testuser' and surface1 should be listed
    #
    surface = Surface.objects.get(name="Surface 1", creator__username=username)
    topos = Topography.objects.filter(surface=surface)

    url = reverse("manager:surface-api-detail", kwargs=dict(pk=surface.pk))
    response = api_client.get(
        f"{url}?children=yes"
    )  # We need children=yes to get the topography set
    assert response.status_code == 200, response.content

    topo_names = [t["name"] for t in response.data["topography_set"]]
    topo_urls = [t["url"] for t in response.data["topography_set"]]
    for t in topos:
        # currently 'listed' means: name in list
        assert t.name in topo_names

        # click on a bar should lead to details, so URL must be included
        url = reverse("manager:topography-api-detail", kwargs=dict(pk=t.pk))
        assert f"http://testserver{url}" in topo_urls


@pytest.fixture
def topo_example3(two_topos):
    return Topography.objects.get(name="Example 3 - ZSensor")


@pytest.fixture
def topo_example4(two_topos):
    return Topography.objects.get(name="Example 4 - Default")


@pytest.mark.django_db
def test_edit_topography(api_client, topo_example3, handle_usage_statistics):
    new_name = "This is a better name"
    new_measurement_date = "2018-07-01"
    new_description = "New results available"

    username = "testuser"
    password = "abcd$1234"

    assert api_client.login(username=username, password=password)

    #
    # First get the form and look whether all the expected data is in there
    #
    response = api_client.get(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topo_example3.pk))
    )
    assert response.status_code == 200, response.content

    assert response.data["name"] == topo_example3.name
    assert response.data["measurement_date"] == str(datetime.date(2018, 1, 1))
    assert response.data["description"] == "description1"
    assert response.data["size_x"] == approx(10000)
    assert response.data["size_y"] == approx(10000)
    assert response.data["unit"] == "nm"
    assert response.data["height_scale"] == approx(0.29638271279074097)
    assert response.data["detrend_mode"] == "height"

    #
    # Then send a post with updated data
    #
    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topo_example3.pk)),
        {
            "data_source": 0,
            "name": new_name,
            "measurement_date": new_measurement_date,
            "description": new_description,
            "detrend_mode": "height",
            "tags": ["ab", "bc"],
            "instrument_type": Topography.INSTRUMENT_TYPE_UNDEFINED,
            "fill_undefined_data_mode": Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING,
            "has_undefined_data": False,
        },
    )
    assert response.status_code == 200, response.content

    #
    # let's check whether it has been changed
    #
    topos = Topography.objects.filter(surface=topo_example3.surface).order_by("pk")

    assert len(topos) == 1

    t = topos[0]

    assert t.measurement_date == datetime.date(2018, 7, 1)
    assert t.description == new_description
    assert t.name == new_name
    assert "example3" in t.datafile.filename
    assert t.unit == "nm"
    assert t.tags == ["ab", "bc"]

    # the changed topography should also appear in the list of topographies
    url = reverse("manager:surface-api-detail", kwargs=dict(pk=t.surface.pk))
    response = api_client.get(f"{url}?children=yes")
    assert response.data["topography_set"][0]["name"] == new_name


@pytest.mark.django_db
def test_edit_line_scan(
    api_client, one_line_scan, django_user_model, handle_usage_statistics
):
    new_name = "This is a better name"
    new_measurement_date = "2018-07-01"
    new_description = "New results available"

    username = "testuser"
    password = "abcd$1234"

    topo_id = one_line_scan.id

    assert api_client.login(username=username, password=password)

    #
    # First get the form and look whether all the expected data is in there
    #
    response = api_client.get(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topo_id))
    )
    assert response.status_code == 200, response.content

    assert response.data["name"] == "Simple Line Scan"
    assert response.data["measurement_date"] == str(datetime.date(2018, 1, 1))
    assert response.data["description"] == "description1"
    assert response.data["size_x"] == 9
    assert response.data["height_scale"] == approx(1.0)
    assert response.data["detrend_mode"] == "height"
    assert response.data["size_y"] is None  # should have been removed by __init__
    assert not response.data["is_periodic"]

    #
    # Then send a patch with updated data
    #
    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topo_id)),
        {
            "data_source": 0,
            "name": new_name,
            "measurement_date": new_measurement_date,
            "description": new_description,
            "height_scale": 0.1,
            "detrend_mode": "height",
            "instrument_type": Topography.INSTRUMENT_TYPE_UNDEFINED,
            "fill_undefined_data_mode": Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING,
            "has_undefined_data": False,
        },
    )
    assert response.status_code == 200, response.content

    # due to the changed topography editing, we should stay on update page
    url = reverse("manager:topography-api-detail", kwargs=dict(pk=topo_id))
    assert f"http://testserver{url}" == response.data["url"]

    topos = Topography.objects.filter(surface__creator__username=username).order_by(
        "pk"
    )

    assert len(topos) == 1

    t = topos[0]

    assert t.measurement_date == datetime.date(2018, 7, 1)
    assert t.description == new_description
    assert t.name == new_name
    assert "line_scan_1" in t.datafile.filename
    assert t.size_y is None

    #
    # should also appear in the list of topographies
    #
    url = reverse("manager:surface-api-detail", kwargs=dict(pk=t.surface.pk))
    response = api_client.get(f"{url}?children=yes")
    assert response.data["topography_set"][0]["name"] == new_name


@pytest.mark.django_db
def test_topography_detail(
    api_client, two_topos, django_user_model, topo_example4, handle_usage_statistics
):
    username = "testuser"
    password = "abcd$1234"

    topo_pk = topo_example4.pk

    django_user_model.objects.get(username=username)

    assert api_client.login(username=username, password=password)

    response = api_client.get(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topo_pk))
    )
    assert response.status_code == 200, response.content

    # resolution should be written somewhere
    assert response.data["resolution_x"] == 75
    assert response.data["resolution_y"] == 305

    # .. as well as detrending mode
    assert response.data["detrend_mode"] == "height"

    # .. description
    assert response.data["description"] == "description2"

    # .. physical size
    assert response.data["unit"] == "m"
    assert response.data["size_x"] == approx(2.773965e-05)
    assert response.data["size_y"] == approx(0.00011280791)


@pytest.mark.django_db
def test_delete_topography(
    api_client, two_topos, topo_example3, handle_usage_statistics
):
    username = "testuser"
    password = "abcd$1234"

    # topography 1 is still in database
    topo = topo_example3

    # single surface, hence there should be on permission set
    assert Surface.objects.count() == 2
    assert PermissionSet.objects.count() == 2

    # make squeezed datafile
    topo.refresh_cache()

    # store names of files in storage system
    pk = topo.pk
    topo_datafile_name = topo.datafile.file.name
    squeezed_datafile_name = topo.squeezed_datafile.file.name
    thumbnail_name = topo.thumbnail.file.name

    # check that files actually exist
    assert default_storage.exists(topo_datafile_name)
    assert default_storage.exists(squeezed_datafile_name)
    assert default_storage.exists(thumbnail_name)
    file = topo.deepzoom.find_file("dzi.json")
    assert file
    dzi_json = file.file.name
    assert default_storage.exists(dzi_json)
    file = topo.deepzoom.find_file("dzi_files/0/0_0.jpg")
    assert file
    dzi_0_0 = file.file.name
    assert default_storage.exists(dzi_0_0)

    assert api_client.login(username=username, password=password)

    api_client.delete(reverse("manager:topography-api-detail", kwargs=dict(pk=pk)))

    # We delete a topography; permission sets are only removed when the surface is
    # removed
    assert PermissionSet.objects.count() == 2

    # topography topo_id is no more in database
    assert not Topography.objects.filter(pk=pk).exists()

    # topography file should also be deleted
    assert not default_storage.exists(topo_datafile_name)
    assert not default_storage.exists(squeezed_datafile_name)
    assert not default_storage.exists(thumbnail_name)
    assert not default_storage.exists(dzi_json)
    assert not default_storage.exists(dzi_0_0)


@pytest.mark.django_db
def test_only_positive_size_values_on_edit(api_client, handle_usage_statistics):
    #
    # prepare database
    #
    username = "testuser"
    password = "abcd$1234"

    user = UserFactory(username=username, password=password)
    surface = SurfaceFactory(creator=user)
    topography = Topography2DFactory(
        surface=surface, size_x=1024, size_y=1024, size_editable=True
    )

    assert api_client.login(username=username, password=password)

    #
    # Then send a patch with negative size values
    #
    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topography.pk)),
        {
            "data_source": topography.data_source,
            "name": topography.name,
            "measurement_date": topography.measurement_date,
            "description": topography.description,
            "size_x": -500.0,  # negative, should be > 0
            "size_y": 0,  # zero, should be > 0
            "height_scale": 0.1,
            "detrend_mode": "height",
            "instrument_type": Topography.INSTRUMENT_TYPE_UNDEFINED,
            "instrument_parameters": {},
            "instrument_name": "",
        },
    )
    assert response.status_code == 400, response.content
    assert (
        response.data["size_x"][0].title()
        == "Ensure This Value Is Greater Than Or Equal To 0.0."
    )


#######################################################################
# Surfaces
#######################################################################


@pytest.mark.django_db
def test_edit_surface(api_client):
    category = "sim"

    user = UserFactory()
    surface = SurfaceFactory(creator=user, category=category)

    api_client.force_login(user)

    new_name = "This is a better surface name"
    new_description = "This is new description"
    new_category = "dum"

    response = api_client.patch(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface.id)),
        {"name": new_name, "description": new_description, "category": new_category},
    )
    assert response.status_code == 200

    surface = Surface.objects.get(pk=surface.id)

    assert new_name == surface.name
    assert new_description == surface.description
    assert new_category == surface.category


@pytest.mark.django_db
def test_delete_surface(api_client, one_topography, handle_usage_statistics):
    user, surface, topo = one_topography
    api_client.force_login(user)

    topo.refresh_cache()

    assert Surface.objects.count() == 1
    assert PermissionSet.objects.count() == 1
    assert Folder.objects.count() == 3  # 1x deepzoom, 2x attachments
    assert Manifest.objects.count() > 0

    response = api_client.delete(
        reverse("manager:surface-api-detail", kwargs=dict(pk=surface.id))
    )
    assert response.status_code == 204, response.content

    assert Surface.objects.all().count() == 0
    assert PermissionSet.objects.count() == 0
    assert Folder.objects.count() == 0
    assert Manifest.objects.count() == 0


@pytest.mark.django_db
def test_v1_download_surface(api_client, handle_usage_statistics):
    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    Topography1DFactory(surface=surface)
    Topography2DFactory(surface=surface)

    api_client.force_login(user)

    response = api_client.get(
        reverse("manager:surface-download", kwargs=dict(surface_ids=surface.id)),
        follow=True,
    )
    assert response.status_code == 200
    assert (
        response["Content-Disposition"]
        == f'attachment; filename="{slugify(surface.name) + ".zip"}"'
    )


@pytest.mark.django_db
def test_v1_download_tag(api_client, handle_usage_statistics):
    user = UserFactory()
    tag = TagFactory(name="test_tag")
    surface = SurfaceFactory(creator=user, tags=[tag])
    Topography1DFactory(surface=surface)
    Topography2DFactory(surface=surface)

    api_client.force_login(user)

    response = api_client.get(
        reverse("manager:tag-download", kwargs=dict(name=tag.name)),
        follow=True,
    )
    assert response.status_code == 200, response.reason_phrase
    assert (
        response["Content-Disposition"]
        == f'attachment; filename="{slugify(tag.name) + ".zip"}"'
    )


@pytest.mark.django_db
def test_v2_download_surface(api_client, settings, handle_usage_statistics, django_capture_on_commit_callbacks):
    settings.CELERY_TASK_ALWAYS_EAGER = True

    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    Topography1DFactory(surface=surface)
    Topography2DFactory(surface=surface)

    api_client.force_login(user)

    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.get(
            reverse("manager:surface-download-v2", kwargs=dict(surface_ids=surface.id)),
            follow=True,
        )
    assert response.status_code == 200, response.reason_phrase
    assert "manifest_url" in response.data
    assert response.data["task_state"] == "pe"
    response = api_client.get(response.data["url"])
    assert response.status_code == 200, response.reason_phrase
    assert "manifest_url" in response.data
    assert response.data["task_state"] == "su"
    response = api_client.get(response.data["manifest_url"])
    assert response.status_code == 200, response.reason_phrase
    assert "file" in response.data


@pytest.mark.django_db
def test_v2_download_tag(api_client, settings, handle_usage_statistics, django_capture_on_commit_callbacks):
    settings.CELERY_TASK_ALWAYS_EAGER = True

    user = UserFactory()
    tag = TagFactory(name="test_tag")
    surface = SurfaceFactory(creator=user, tags=[tag])
    Topography1DFactory(surface=surface)
    Topography2DFactory(surface=surface)

    api_client.force_login(user)

    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.get(
            reverse("manager:tag-download-v2", kwargs=dict(name=tag.name)),
            follow=True,
        )
    assert response.status_code == 200, response.reason_phrase
    assert "manifest_url" in response.data
    assert response.data["task_state"] == "pe"
    response = api_client.get(response.data["url"])
    assert response.status_code == 200, response.reason_phrase
    assert "manifest_url" in response.data
    assert response.data["task_state"] == "su"
    response = api_client.get(response.data["manifest_url"])
    assert response.status_code == 200, response.reason_phrase
    assert "file" in response.data


@pytest.mark.django_db
def test_automatic_extraction_of_measurement_date(
    api_client, settings, handle_usage_statistics, django_capture_on_commit_callbacks
):
    settings.CELERY_TASK_ALWAYS_EAGER = True  # perform tasks locally

    name = "plux-1.plux"
    input_file_path = Path(
        f"{FIXTURE_DATA_DIR}/{name}"
    )  # maybe use package 'pytest-datafiles' here instead

    user = UserFactory()
    surface = SurfaceFactory(creator=user)

    api_client.force_login(user)

    # Upload file
    response = upload_topography_file(
        str(input_file_path), surface.id, api_client, django_capture_on_commit_callbacks
    )

    # Check that the measurement date was populated automatically
    assert response.data["name"] == "plux-1.plux"
    assert response.data["measurement_date"] == "2022-05-16"

    # Update measurement date
    topography_id = response.data["id"]
    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topography_id)),
        {"measurement_date": "2018-06-21"},
    )
    assert response.status_code == 200, response.content
    assert response.data["measurement_date"] == "2018-06-21"

    # Force reparsing the data file
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.post(
            reverse("manager:force-inspect", kwargs=dict(pk=topography_id))
        )
        assert response.status_code == 200, response.content
    assert len(callbacks) == 1

    # Check that measurement date was not overriden
    response = api_client.get(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topography_id))
    )
    assert response.status_code == 200, response.content
    assert response.data["measurement_date"] == "2018-06-21"


@pytest.mark.django_db
def test_automatic_extraction_of_instrument_parameters(
    api_client, settings, handle_usage_statistics, django_capture_on_commit_callbacks
):
    name = "dektak-1.csv"
    input_file_path = Path(
        f"{FIXTURE_DATA_DIR}/{name}"
    )  # maybe use package 'pytest-datafiles' here instead

    user = UserFactory()
    surface = SurfaceFactory(creator=user)

    api_client.force_login(user)

    # Upload file
    response = upload_topography_file(
        str(input_file_path), surface.id, api_client, django_capture_on_commit_callbacks
    )

    # Check that the instrument parameters were populated automatically
    assert response.data["name"] == "dektak-1.csv"
    assert response.data["instrument_parameters"] == {
        "tip_radius": {
            "value": 2.5,
            "unit": "µm",
        }
    }

    # Update tip radius
    new_instrument_parameters = {"tip_radius": {"value": 3, "unit": "m"}}

    topography_id = response.data["id"]
    response = api_client.patch(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topography_id)),
        {"instrument_parameters": new_instrument_parameters},
    )
    assert response.status_code == 200, response.content
    assert response.data["instrument_parameters"] == new_instrument_parameters
    assert response.data["instrument_type"] == Topography.INSTRUMENT_TYPE_CONTACT_BASED

    # Force reparsing the data file
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.post(
            reverse("manager:force-inspect", kwargs=dict(pk=topography_id))
        )
        assert response.status_code == 200, response.content
    assert len(callbacks) == 1

    # Check that instrument parameters were not overriden
    response = api_client.get(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topography_id))
    )
    assert response.status_code == 200, response.content
    assert response.data["instrument_parameters"] == new_instrument_parameters
    assert response.data["instrument_type"] == Topography.INSTRUMENT_TYPE_CONTACT_BASED


@pytest.mark.django_db
def test_squeezed_creation_fails(mocker):
    topo = Topography2DFactory(size_x=1, size_y=1)
    topo.refresh_cache()
    # should have a thumbnail picture
    assert topo.squeezed_datafile is not None

    mocker.patch(
        "topobank.manager.models.Topography._make_squeezed",
        side_effect=Exception("Test exception"),
    )
    topo.refresh_cache()
    # should have no thumbnail picture
    assert topo.squeezed_datafile is None

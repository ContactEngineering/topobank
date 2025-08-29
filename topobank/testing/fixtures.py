#
# Common settings and fixtures used with pytest
#

import datetime
import logging
import tempfile

import numpy as np
import pytest
from django.core.management import call_command
from pytest_django.lazy_django import skip_if_no_django
from SurfaceTopography import NonuniformLineScan as STNonuniformLineScan
from SurfaceTopography import Topography as STTopography
from trackstats.models import Domain, Metric

from ..manager.models import Surface
from .factories import (
    ManifestFactory,
    OrganizationFactory,
    SurfaceFactory,
    TagFactory,
    Topography1DFactory,
    Topography2DFactory,
    UserFactory,
)

_log = logging.getLogger(__name__)


PASSWORD = "secret"


@pytest.fixture
def handle_usage_statistics():
    """This fixture is needed in the supplib which affect usage statistics.
    Otherwise, you get a foreign key error because entries remain
    without a corresponding foreign key in the metric table.

    Returns
    -------
        None
    """
    from ..usage_stats.utils import register_metrics

    register_metrics()
    yield
    #
    # Teardown code which is run after the test function
    #
    Domain.objects.clear_cache()
    Metric.objects.clear_cache()


@pytest.fixture(scope="function")
def user_alice():
    return UserFactory(username="alice", password=PASSWORD, name="Alice Wonderland")


@pytest.fixture(scope="function")
def user_bob():
    return UserFactory(username="bob", password=PASSWORD, name="Bob Marley")


@pytest.fixture(scope="function")
def user_staff():
    return UserFactory(
        username="staff", password=PASSWORD, name="Admin User", is_staff=True
    )


@pytest.fixture(scope="function")
def org_blofield():
    return OrganizationFactory(name="blofield")


@pytest.fixture(scope="function")
def user_alice_logged_in(live_server, browser, user_alice, handle_usage_statistics):
    # passing "handle_usage_statistics" is important, otherwise
    # the following supplib may fail in a strange way because of foreign key errors

    browser.visit(
        live_server.url + "/accounts/login"
    )  # we don't want to use ORCID here for testing

    assert browser.is_element_present_by_text("Sign In", wait_time=1)

    #
    # Logging in
    #
    browser.fill("login", user_alice.username)
    browser.fill("password", PASSWORD)
    browser.find_by_text("Sign In").last.click()

    try:
        yield browser, user_alice
    finally:
        #
        # Logging out
        #
        # important to have new session on next login
        browser.find_by_id("userDropdown", wait_time=5).click()  # may cause problems..
        browser.find_by_text("Sign Out").first.click()
        browser.is_element_present_by_text("Ready to Leave?", wait_time=1)
        browser.find_by_text("Sign Out").last.click()

        browser.is_element_present_by_text("You have signed out.", wait_time=1)
        browser.quit()

        # remove session variables for user alice such these do no
        # affect subsequent supplib
        call_command("clearsessions")  # TODO is this effective?
        _log.info("Cleared all sessions.")


#
# Define fixtures
#
@pytest.fixture
def two_topos(settings):
    call_command("register_analysis_functions")

    user = UserFactory(username="testuser", password="abcd$1234")
    surface1 = SurfaceFactory(name="Surface 1", creator=user)
    surface2 = SurfaceFactory(name="Surface 2", creator=user)

    settings.DELETE_EXISTING_FILES = True  # There can be remnants from failed tests
    datafile1 = ManifestFactory(filename="example3.di")
    datafile2 = ManifestFactory(filename="example4.txt")

    topos1 = Topography2DFactory(
        surface=surface1,
        creator=user,
        name="Example 3 - ZSensor",
        data_source=0,
        measurement_date=datetime.date(2018, 1, 1),
        description="description1",
        size_x=10.0,
        size_y=10.0,
        size_editable=True,  # needed for supplib
        unit="µm",
        detrend_mode="height",
        height_scale_editable=False,  # height_scale_factor defined in DI file
        height_scale=0.296382712790741,  # workaround: mentioned here so it is correctly set
        # normally this would be set during the upload process
        datafile=datafile1,
        resolution_x=256,
        resolution_y=256,
    )

    topos2 = Topography2DFactory(
        surface=surface2,
        creator=user,
        name="Example 4 - Default",
        data_source=0,
        measurement_date=datetime.date(2018, 1, 2),
        description="description2",
        size_x=112.80791,
        size_y=27.73965,
        unit="µm",
        detrend_mode="height",
        height_scale=2.91818e-08,  # workaround: mentioned here so it is correctly set
        height_scale_editable=False,  # defined in TXT file
        datafile=datafile2,
        resolution_x=75,
        resolution_y=305,
    )
    return topos1, topos2


@pytest.fixture
def one_line_scan():
    user = UserFactory(username="testuser", password="abcd$1234")
    surface = Surface(name="Line Scans", creator=user)
    surface.save()

    datafile = ManifestFactory(filename="line_scan_1.asc")

    return Topography1DFactory(
        surface=surface,
        name="Simple Line Scan",
        measurement_date=datetime.date(2018, 1, 1),
        description="description1",
        size_x=9,
        size_editable=True,  # needed for test
        detrend_mode="height",
        datafile=datafile,
    )


@pytest.fixture
def one_topography():
    user = UserFactory(username="testuser", password="abcd$1234")
    surface = Surface(name="Line Scans", creator=user)
    surface.save()

    datafile = ManifestFactory(filename="example.opd")

    topo = Topography1DFactory(
        surface=surface,
        name="Topography Map",
        description="description1",
        datafile=datafile,
    )
    return user, surface, topo


@pytest.fixture
def topography_loaded_from_broken_file():
    topo = Topography1DFactory()

    from django.core.files.base import ContentFile

    new_content = ContentFile(
        "\x00"
    )  # some nonsense which cannot be interpreted by module "SurfaceTopography"
    with tempfile.NamedTemporaryFile(mode="wb") as tmp:
        topo.datafile.save(tmp.name, new_content)

    return topo


@pytest.fixture
def user_three_topographies_three_surfaces_three_tags():
    user = UserFactory()

    tag1 = TagFactory()
    tag2 = TagFactory()
    tag3 = TagFactory()

    tag1.authorize_user(user, "view")
    tag2.authorize_user(user, "view")
    tag3.authorize_user(user, "view")

    surface1 = SurfaceFactory(creator=user, tags=[tag1])
    topo1a = Topography1DFactory(surface=surface1)
    topo1b = Topography1DFactory(surface=surface1, tags=[tag2, tag3])

    surface2 = SurfaceFactory(creator=user, tags=[tag2])
    topo2a = Topography1DFactory(surface=surface2, tags=[tag1])

    surface3 = SurfaceFactory(creator=user, tags=[tag3])  # empty

    return (
        user,
        (topo1a, topo1b, topo2a),
        (surface1, surface2, surface3),
        (tag1, tag2, tag3),
    )


@pytest.fixture
def two_users(settings):
    settings.DELETE_EXISTING_FILES = True  # There can be remnants from failed tests

    user1 = UserFactory(username="testuser1", password="abcd$1234")
    user2 = UserFactory(username="testuser2", password="abcd$1234")

    surface1 = SurfaceFactory(creator=user1)
    Topography1DFactory(surface=surface1)

    surface2 = SurfaceFactory(creator=user2)
    Topography1DFactory(surface=surface2)

    surface3 = SurfaceFactory(creator=user2)
    Topography1DFactory(surface=surface3)

    return (user1, user2), (surface1, surface2, surface3)


@pytest.fixture(scope="function", autouse=True)
def sync_analysis_functions(db):
    _log.info("Syncing analysis functions in registry with database objects..")
    from ..analysis.registry import sync_implementation_classes

    sync_implementation_classes(cleanup=True)
    _log.info("Done synchronizing registry with database.")


@pytest.fixture(scope="function")
def test_analysis_function(sync_analysis_functions):
    from ..analysis.models import Workflow

    return Workflow.objects.get(name="topobank.testing.test")


@pytest.fixture
def example_authors():
    authors = [
        {
            "first_name": "Hermione",
            "last_name": "Granger",
            "orcid_id": "9999-9999-9999-999X",
            "affiliations": [{"name": "Hogwarts"}],
        },
        {
            "first_name": "Harry",
            "last_name": "Potter",
            "orcid_id": "9999-9999-9999-9999",
            "affiliations": [
                {"name": "University of Freiburg", "ror_id": "0245cg223"},
                {"name": "Hogwarts"},
            ],
        },
    ]
    return authors


@pytest.fixture()
def use_dummy_cache_backend(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.dummy.DummyCache",
        }
    }


@pytest.fixture()
def api_rf():
    """APIRequestFactory instance"""
    skip_if_no_django()

    from rest_framework.test import APIRequestFactory

    return APIRequestFactory()


@pytest.fixture()
def api_client():
    """APIClient instance"""
    skip_if_no_django()

    from rest_framework.test import APIClient

    # We don't want to raise exceptions in tests, because we want to check
    # the response status code
    return APIClient(raise_request_exception=False)


@pytest.fixture
def simple_linear_2d_topography():
    """Simple 2D topography, which is linear in y"""
    unit = "nm"
    y = np.arange(10).reshape((1, -1))
    x = np.arange(5).reshape((-1, 1))
    arr = -2 * y + 0 * x  # only slope in y direction
    t = STTopography(arr, (5, 10), unit=unit).detrend("center")
    return t


@pytest.fixture
def simple_surface():
    class WrapTopography:
        def __init__(self, t):
            self._t = t

        def topography(self):
            return self._t

    class WrapRequest:
        def __init__(self, c):
            self._c = c

        def all(self):
            return self._c

    class WrapSurface:
        def __init__(self, c):
            self._c = c

        @property
        def topography_set(self):
            return WrapRequest(self._c)

    nx, ny = 113, 123
    sx, sy = 1, 1
    lx = 0.3
    topographies = [
        STTopography(
            np.resize(np.sin(np.arange(nx) * sx * 2 * np.pi / (nx * lx)), (nx, ny)),
            (sx, sy),
            periodic=False,
            unit="um",
        )
    ]

    nx = 278
    sx = 100
    lx = 2
    x = np.arange(nx) * sx / nx
    topographies += [STNonuniformLineScan(x, np.cos(x * np.pi / lx), unit="nm")]

    return WrapSurface([WrapTopography(t) for t in topographies])


@pytest.mark.django_db
@pytest.fixture
def test_instances(test_analysis_function):
    users = [UserFactory(username="user1"), UserFactory(username="user2")]

    surfaces = [
        SurfaceFactory(creator=users[0]),
        SurfaceFactory(creator=users[0]),
    ]

    topographies = [Topography1DFactory(surface=surfaces[0])]

    test_analysis_function.submit(topographies[0].creator, topographies[0])

    return users, surfaces, topographies

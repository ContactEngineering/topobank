#
# Common settings and fixtures used with pytest
#

import logging

import pytest
from django.core.management import call_command
from pytest_django.lazy_django import skip_if_no_django
from trackstats.models import Domain, Metric

from .users.tests.factories import UserFactory

_log = logging.getLogger(__name__)

PASSWORD = "secret"


@pytest.fixture
def handle_usage_statistics():
    """This fixture is needed in the tests which affect usage statistics.
    Otherwise, you get a foreign key error because entries remain
    without a corresponding foreign key in the metric table.

    Returns
    -------
        None
    """
    from .usage_stats.utils import register_metrics
    register_metrics()
    yield
    #
    # Teardown code which is run after the test function
    #
    Domain.objects.clear_cache()
    Metric.objects.clear_cache()


@pytest.fixture(scope='function')
def user_alice():
    return UserFactory(username='alice', password=PASSWORD, name='Alice Wonderland')


@pytest.fixture(scope='function')
def user_bob():
    return UserFactory(username='bob', password=PASSWORD, name='Bob Marley')


@pytest.fixture(scope='function')
def user_alice_logged_in(live_server, browser, user_alice, handle_usage_statistics):
    # passing "handle_usage_statistics" is important, otherwise
    # the following tests may fail in a strange way because of foreign key errors

    browser.visit(live_server.url + "/accounts/login")  # we don't want to use ORCID here for testing

    assert browser.is_element_present_by_text('Sign In', wait_time=1)

    #
    # Logging in
    #
    browser.fill('login', user_alice.username)
    browser.fill('password', PASSWORD)
    browser.find_by_text('Sign In').last.click()

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

        browser.is_element_present_by_text('You have signed out.', wait_time=1)
        browser.quit()

        # remove session variables for user alice such these do no
        # affect subsequent tests
        call_command('clearsessions')  # TODO is this effective?
        _log.info("Cleared all sessions.")


@pytest.fixture(scope="function", autouse=True)
def sync_analysis_functions(db):
    _log.info("Syncing analysis functions in registry with database objects..")
    from .analysis.registry import AnalysisRegistry
    reg = AnalysisRegistry()
    reg.sync_analysis_functions(cleanup=True)
    _log.info("Done synchronizing registry with database.")


@pytest.fixture(scope="function")
def test_analysis_function(db, sync_analysis_functions):
    from .analysis.models import AnalysisFunction
    return AnalysisFunction.objects.get(name="test")


@pytest.fixture
def example_authors():
    authors = [
        {
            'first_name': 'Hermione',
            'last_name': 'Granger',
            'orcid_id': '9999-9999-9999-999X',
            'affiliations': [
                {
                    'name': 'Hogwarts'
                }
            ]
        },
        {'first_name': 'Harry',
         'last_name': 'Potter',
         'orcid_id': '9999-9999-9999-9999',
         'affiliations': [
             {
                 'name': 'University of Freiburg',
                 'ror_id': '0245cg223'
             },
             {
                 'name': 'Hogwarts'
             }
         ]
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

    return APIClient()

#
# Common settings and fixtures used with pytest
#
import pytest
from django.core.management import call_command
import logging

from trackstats.models import Domain, Metric

from topobank.analysis.registry import AnalysisFunctionRegistry
from topobank.manager.tests.utils import UserFactory

_log = logging.getLogger(__name__)

PASSWORD = "secret"


@pytest.fixture
def handle_usage_statistics():
    """This fixture is needed in the tests which affect usage statistics.
    Otherwise you get a foreign key error because entries remain
    without a corresponding foreign key in the metric table.

    Returns
    -------
        None
    """
    from topobank.usage_stats.utils import register_metrics
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

    #
    # Register all analysis functions
    #
    reg = AnalysisFunctionRegistry()
    reg.sync()

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


@pytest.fixture(autouse=True)
def reset_singletons():
    from topobank.analysis.functions import AnalysisFunctionRegistry
    reg = AnalysisFunctionRegistry()
    del reg



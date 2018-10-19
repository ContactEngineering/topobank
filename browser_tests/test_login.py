
import pytest

@pytest.mark.django_db
def test_login_logout(live_server, webdriver, no_surfaces_testuser_signed_in):
    pass # all the work is done in the fixture "no_surfaces_testuser_signed_in"


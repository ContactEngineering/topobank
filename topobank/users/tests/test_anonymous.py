import pytest
from django.shortcuts import reverse
from django.utils import timezone
from django.contrib import auth

from topobank.utils import assert_in_content, assert_not_in_content
from termsandconditions.models import TermsAndConditions


@pytest.mark.django_db
def test_terms_conditions_as_anonymous(client):

    # Install terms and conditions for test
    TermsAndConditions.objects.create(slug='test-terms', name="Test of T&amp;C",
                                      text="some text", date_active=timezone.now())

    response = client.get(reverse('terms'))

    assert_in_content(response, "Test of T&amp;C")
    assert_in_content(response, "some text")

@pytest.mark.django_db
def test_no_intermediate_login_page_when_not_logged_in_and_pressing_surfaces(client):

    # user is not yet logged in
    user = auth.get_user(client)
    assert not user.is_authenticated

    # pressing box saying "number of surfaces in database"
    response = client.get(reverse('manager:surface-list'), follow=True)

    # make sure that the message of intermediate page *doesn't* appear
    assert_not_in_content(response, 'existing third party accounts')
    assert_not_in_content(response, 'Sign In')
    assert_not_in_content(response, 'Username')
    assert_not_in_content(response, 'Password')

    # we want a redirection to ORCID instead
    assert response.status_code == 302





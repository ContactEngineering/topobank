import pytest
from django.shortcuts import reverse
from django.utils import timezone
from django.contrib import auth
from django.utils.http import urlencode

from topobank.utils import assert_in_content, assert_not_in_content
from topobank.manager.tests.utils import UserFactory
from termsandconditions.models import TermsAndConditions


@pytest.mark.django_db
def test_terms_conditions_as_anonymous(client):

    # Install terms and conditions for test
    TermsAndConditions.objects.create(slug='test-terms', name="Test of T&amp;C",
                                      text="some text", date_active=timezone.now())

    response = client.get(reverse('terms'))
    assert_in_content(response, "Test of T&amp;C")

    response = client.get(reverse('tc_accept_specific_page', kwargs=dict(slug='test-terms')))
    assert_in_content(response, "some text")


@pytest.mark.django_db
def test_no_intermediate_login_page_when_not_logged_in_and_pressing_surfaces(client):

    #
    # This test was added because of GH 423.
    #

    # user is not yet logged in
    user = auth.get_user(client)
    assert not user.is_authenticated

    response = client.get(reverse('home'))

    #
    # make sure some reference to orcid is in the added links
    #
    assert "orcid" in response.context['surfaces_link']
    assert "orcid" in response.context['analyses_link']

    #
    # make sure the links redirect to surfaces/analyses
    #
    surfaces_next = urlencode({'method':'oauth2', 'next': reverse('manager:select')})
    analyses_next = urlencode({'method':'oauth2', 'next': reverse('analysis:list')})

    assert surfaces_next in response.context['surfaces_link']
    assert analyses_next in response.context['analyses_link']

    #
    # make sure these links are used
    #
    assert_in_content(response, response.context['surfaces_link'].replace('&', '&amp;'))
    assert_in_content(response, response.context['analyses_link'].replace('&', '&amp;'))

    #
    # The following would be the test for a better implementation,
    # which is possible when https://github.com/pennersr/django-allauth/issues/345
    # is resolved (or by another workaround).
    #
    # response = client.get(reverse('manager:select'), follow=True)
    #
    # # make sure that the message of intermediate page *doesn't* appear
    # assert_not_in_content(response, 'existing third party accounts')
    # assert_not_in_content(response, 'Sign In')
    # assert_not_in_content(response, 'Username')
    # assert_not_in_content(response, 'Password')
    #
    # # we want a redirection to ORCID instead
    # assert response.status_code == 302

    # When logged in, the special links should not be included any more
    user = UserFactory()
    client.force_login(user)
    response = client.get(reverse('home'))

    assert "orcid" not in response.context['surfaces_link']
    assert "orcid" not in response.context['analyses_link']





import pytest

from django.shortcuts import reverse
from guardian.shortcuts import get_anonymous_user

from topobank.tabnav.templatetags.tabnav_tags import tab_navigation
from topobank.utils import assert_in_content, assert_not_in_content
from topobank.manager.tests.utils import UserFactory


@pytest.mark.parametrize("should_be_visible", [True, False])
@pytest.mark.django_db
def test_display_own_publications_tab(settings, rf, should_be_visible, handle_usage_statistics):
    settings.PUBLICATION_DISPLAY_TAB_WITH_OWN_PUBLICATIONS = should_be_visible

    user = UserFactory()
    request = rf.get(reverse('home'))
    request.user = user
    request.session = {}

    from topobank.views import HomeView
    response = HomeView.as_view()(request)
    response.render()

    if should_be_visible:
        assert_in_content(response, 'bullhorn')
    else:
        assert_not_in_content(response, 'bullhorn')
    # bullhorn is the name of the logo used in the tab



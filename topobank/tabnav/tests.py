import pytest

from topobank.tabnav.templatetags.tabnav_tags import tab_navigation

def test_tab_navigation_tag(rf):

    request = rf.get('/somepage')

    class User:

        def __init__(self, authenticated):
            self._authenticated = authenticated

        @property
        def is_authenticated(self):
            return self._authenticated

    request.user = User(True)

    context = {
        'request': request,
        'extra_tabs': [
            {
                'title': 'Analyze',
                'icon': 'area-chart',
            }
        ]
    }

    tag_context = tab_navigation(context)

    assert tag_context['tabs'] == [
        {
            'title': 'Analyze',
            'icon': 'area-chart',
            'active': True,
            'href': '/somepage',
            'login_required': True
        }
    ]

    #
    # If the user is not authenticated, the tab should be missing,
    # because the default is that login is required
    #
    request.user = User(False)
    tag_context = tab_navigation(context)

    assert tag_context['tabs'] == []




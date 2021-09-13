import pytest

from topobank.tabnav.templatetags.tabnav_tags import tab_navigation

def test_tab_navigation_tag(rf):

    request = rf.get('/somepage')

    class User:

        def __init__(self, anonymous):
            self._anonymous = anonymous

        @property
        def is_anonymous(self):
            return self._anonymous

    request.user = User(True)

    context = {
        'request': request,
        'extra_tabs': [
            {
                'title': 'Analyze',
                'icon': 'chart-area',
            }
        ]
    }

    tag_context = tab_navigation(context)

    assert tag_context['tabs'] == [
        {
            'title': 'Analyze',
            'icon': 'chart-area',
            'active': True,
            'href': '/somepage',
            'login_required': True
        }
    ]

    #
    # If the user is anonymous, the tab should be missing,
    # because the default is that login is required
    #
    request.user = User(True)
    tag_context = tab_navigation(context)

    assert tag_context['tabs'] == []




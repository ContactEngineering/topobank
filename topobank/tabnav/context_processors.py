from django.shortcuts import reverse

from django.conf import settings

HOME_URL = reverse('home')
SELECT_URL = reverse('manager:select')
SHARING_INFO_URL = reverse('manager:sharing-info')
PUBLICATIONS_URL = reverse('manager:publications')


def fixed_tabs_processor(request):
    """Adds fixed tabs.

    Parameters
    ----------
    request

    Returns
    -------
    Dict with extra context, having a key 'fixed_tabs' containing a list of tabs.

    Each tab is a dict with the following form:

    {
        'login_required': True,  # boolean, if True, tab is only shown to logged-in users
        'title': 'Tab title shown on the tab',
        'icon': 'edit',  # a fontawesome icon name,
        'icon_style_prefix': 'fas',  # class used as prefix for icons, default: 'fas' (=solid)
        'href': '',  # A URL pointing to the view for the tab
        'active': False,  #  a boolean; True means the tab is active
    }
    """

    tabs = [
        {
            'login_required': False,
            'title': '',  # no text
            'icon': 'home',
            'href': HOME_URL,
            'active': request.path == HOME_URL,
            'tooltip': "Welcome to contact.engineering",
            'show_basket': False,
        }
    ]

    if settings.PUBLICATION_DISPLAY_TAB_WITH_OWN_PUBLICATIONS:
        tabs.append(
            {
                'login_required': True,
                'title': '',  # no text
                'icon': 'bullhorn',
                'href': PUBLICATIONS_URL,
                'active': request.path == PUBLICATIONS_URL,
                'tooltip': "Surfaces published by you",
                'show_basket': False,
            },
        )

    tabs.extend([
        {
            'login_required': True,
            'title': '',  # no text
            'icon': 'share-alt',
            'href': SHARING_INFO_URL,
            'active': request.path == SHARING_INFO_URL,
            'tooltip': "Surfaces shared with you or by you",
            'show_basket': False,
        },
        {
            'login_required': False,
            'title': 'Find & select',
            'icon': 'check-square',
            'icon_style_prefix': 'far',
            'href': SELECT_URL,
            'active': request.path == SELECT_URL,
            'tooltip': "Select surfaces and topographies for analysis or create new surfaces",
            'show_basket': True,
        },
    ])

    # Add default value for icon_style_prefix if missing
    for tab in tabs:
        tab.setdefault('icon_style_prefix', 'fas')

    return dict(fixed_tabs=tabs)




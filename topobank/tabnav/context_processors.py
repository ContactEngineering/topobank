from django.shortcuts import reverse

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
        'icon': 'edit'  # a fontawesome icon name,
        'href': ''  # A URL pointing to the view for the tab
        'active': False  #  a boolean; True means the tab is active
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
        },
        {
            'login_required': True,
            'title': '',  # no text
            'icon': 'bullhorn',
            'href': PUBLICATIONS_URL,
            'active': request.path == PUBLICATIONS_URL,
            'tooltip': "Surfaces published by you",
        },
        {
            'login_required': True,
            'title': '',  # no text
            'icon': 'share-alt',
            'href': SHARING_INFO_URL,
            'active': request.path == SHARING_INFO_URL,
            'tooltip': "Surfaces shared with you or by you",
        },
        {
            'login_required': False,
            'title': 'Select',  # no text
            'icon': 'check-square-o',
            'href': SELECT_URL,
            'active': request.path == SELECT_URL,
            'tooltip': "Select surfaces and topographies for analysis or create new surfaces",
        },
    ]
    return dict(fixed_tabs=tabs)




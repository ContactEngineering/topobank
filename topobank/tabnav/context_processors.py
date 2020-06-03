from django.shortcuts import reverse

HOME_URL = reverse('home')
SELECT_URL = reverse('manager:select')
SHARING_INFO_URL = reverse('manager:sharing-info')


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
        'login_required': True,  # boolean, if True, tab is only shown to authenticated users
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
        },
        {
            'login_required': True,
            'title': '',  # no text
            'icon': 'share-alt',
            'href': SHARING_INFO_URL,
            'active': request.path == SHARING_INFO_URL,
        },
        {
            'login_required': True,
            'title': 'Select',  # no text
            'icon': 'check-square-o',
            'href': SELECT_URL,
            'active': request.path == SELECT_URL,
        },
    ]
    return dict(fixed_tabs=tabs)




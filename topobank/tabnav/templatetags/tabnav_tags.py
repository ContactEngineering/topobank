from django import template

register = template.Library()

TABS_CONTEXT_KEYS = ['fixed_tabs', 'extra_tabs']


@register.inclusion_tag('tabnav/tabs.html', takes_context=True)
def tab_navigation(context):
    """Can be used to insert tab navigation on the page.

    Use {% tab_navigation %} in order to include
    navigation by tabs. This function here provides the
    context which is used with the given template.
    """

    if 'request' not in context:
        return {}  # Needed in case of 500 status (server error)

    is_anonymous = context['request'].user.is_anonymous
    request_path = context['request'].path
    active_tab = {}
    tabs = []
    for k in TABS_CONTEXT_KEYS:
        if k in context:
            for tab in context[k]:
                # make sure that all tabs have necessary keys
                tab.setdefault('login_required', True)

                # if user is not authenticated and login is required for
                # this tab, the tab can be excluded
                if tab['login_required'] and is_anonymous:
                    continue  # tab is skipped

                tab.setdefault('href', request_path)
                tab.setdefault('active', tab['href'].startswith(request_path))  # in order to make tab definition short
                tab.setdefault('icon', 'cog')  # just some icon that we see one is missing
                tab.setdefault('title', '')
                tab.setdefault('show_basket', False)
                tabs.append(tab)

                # we want to be able to see variable "show_basket"
                # of the  active tab
                if tab['href'].startswith(request_path):
                    active_tab = tab.copy()

    # calculate minimum number of tabs
    min_num_tabs = len(context['fixed_tabs'])

    if not context.get('connect_fixed_tabs_with_extra_tabs', True):  # default is to connect
        min_num_tabs += 1  # avoid double bracket between fixed and extra tabs -> no connection

    local_context = dict(tabs=tabs, min_num_tabs=min_num_tabs, active_tab=active_tab)
    if 'exception' in context:
        # we want to show exceptions in an own tab
        local_context['error'] = 'error'  # must be not empty for if in template

    return local_context

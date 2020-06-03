from django import template

register = template.Library()

TABS_CONTEXT_KEYS = ['fixed_tabs', 'extra_tabs']

@register.inclusion_tag('tabnav/tabs.html', takes_context=True)
def tab_navigation(context):
    user_authenticated = context['request'].user.is_authenticated
    request_path = context['request'].path
    tabs = []
    for k in TABS_CONTEXT_KEYS:
        if k in context:
            for tab in context[k]:
                # make sure that all tabs have necessary keys
                tab.setdefault('login_required', True)

                # if user is not authenticated and login is required for
                # this tab, the tab can be excluded
                if tab['login_required'] and not user_authenticated:
                    continue  # tab is skipped

                tab.setdefault('href', request_path)
                tab.setdefault('active', tab['href'] == request_path)  # in order to make tab definition short
                tab.setdefault('icon', 'cog')  # just some icon that we see one is missing
                tab.setdefault('title', '')
                tabs.append(tab)
    return dict(tabs=tabs)

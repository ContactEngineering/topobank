from django.urls import resolve
from django import template
register = template.Library()

@register.simple_tag
def navbar_active(url, section):
    """Hardcoded rules for highlighing navbar items.

    The URL of the request is compared to
    allowed urls for the given "section"
    which is a string. If the url is part of the given section,
    the string "active" is returned, otherwise ''.

    :param request:
    :param section: a string, one of ['Surfaces', 'Analyses', 'Sharing' ]
    :return: "active" or ""
    """
    ACTIVE = "active"
    INACTIVE = ""

    resolve_match = resolve(url)

    if (section == "Analyses") and (resolve_match.app_name == "analysis"):
        return ACTIVE

    if (section == "Sharing") and (resolve_match.view_name == "manager:sharing-info"):
        return ACTIVE

    if (section == "Surfaces") and (resolve_match.app_name == "manager") and \
        (resolve_match.view_name != "manager:sharing-info"):
        return ACTIVE

    return INACTIVE






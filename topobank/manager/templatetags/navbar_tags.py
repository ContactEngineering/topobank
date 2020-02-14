from django.urls import resolve
from django.urls.exceptions import Resolver404
from django import template
register = template.Library()

@register.simple_tag
def navbar_active(url, section):
    """Hardcoded rules for highlighing navbar items.

    The URL of the request is compared to
    allowed urls for the given "section"
    which is a string. If the url is part of the given section,
    the string "active" is returned, otherwise ''.

    :param url:
    :param section: a string, one of ['Surfaces', 'Analyses', 'Sharing' ]
    :return: "active" or ""
    """
    ACTIVE = "active"
    INACTIVE = ""

    try:
        resolve_match = resolve(url)
    except Resolver404:
        # we need to aviod a recursion here, see GH 367
        return INACTIVE

    if (section == "Analyses") and (resolve_match.app_name == "analysis"):
        return ACTIVE

    if (section == "Sharing") and (resolve_match.view_name == "manager:sharing-info"):
        return ACTIVE

    if (section == "Surfaces") and (resolve_match.app_name == "manager") and \
        (resolve_match.view_name != "manager:sharing-info"):
        return ACTIVE

    return INACTIVE






from django import template

from django.conf import settings

register = template.Library()

@register.inclusion_tag('publication/license_urls.html')
def render_license_urls(license_choice):
    """Returns a HMTL snippet which can be inserted for the license links.
    """
    license_info = settings.CC_LICENSE_INFOS[license_choice]

    return license_info

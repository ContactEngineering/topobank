from django import template

from django.conf import settings

register = template.Library()

@register.inclusion_tag('manager/license_urls.html')
def render_license_urls(license_choice):
    """Returns a HMTL snippet which can be inserted for the license links.
    """
    license_urls = settings.CC_LICENSE_URLS[license_choice]

    return {
        'description_url': license_urls[0],
        'legal_code_url': license_urls[1],
    }

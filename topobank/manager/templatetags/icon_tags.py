"""
Template tags for displaying icons.
"""
from django import template

register = template.Library()


@register.inclusion_tag('manager/fa5_icon.html')
def fa5_icon(name, style_prefix='fas', title=None):
    """Returns a HMTL snippet which generates an fontawesome 5 icon.

    Parameters:

        style_prefix: str
            'fas' (default) for solid icons, 'far' for regular icons
    """
    return {
        'classes': f'fa-{name} {style_prefix}',
        'title': title,
    }

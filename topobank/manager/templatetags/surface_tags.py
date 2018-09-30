from django import template
from ..utils import selected_topographies as st

register = template.Library()

@register.simple_tag
def selected_topographies(request, surface):
    return st(request, surface=surface)

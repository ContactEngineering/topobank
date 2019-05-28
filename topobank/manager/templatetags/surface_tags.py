from django import template
import json

from ..utils import selected_topographies as st, selection_from_session, bandwidths_data

register = template.Library()

@register.simple_tag
def selected_topographies(request, surface):
    return st(request, surface=surface)

@register.simple_tag
def is_surface_explicitly_selected(request, surface):
    surface_selection_str = "surface-{}".format(surface.id)
    return surface_selection_str in selection_from_session(request.session)

@register.simple_tag
def bandwidths_data_json_for_selected_topographies(request, surface):
    return json.dumps(bandwidths_data(st(request, surface=surface)))

@register.inclusion_tag('manager/yesno.html')
def render_boolean(value, title, show_false=False):
    """Returns a HMTL snippet which can be inserted as True/False symbol.
    """
    return {
        'boolean_value' : value,
        'title': title,
        'show_false': show_false
    }

@register.inclusion_tag('manager/shared_by_badge.html')
def render_shared_by_badge(request, surface):
    """Returns a HMTL snippet with a badge about who shared a given surface.
    """
    return {
        'surface': surface,
        'is_creator': request.user == surface.creator
    }

@register.inclusion_tag('manager/uploaded_by_badge.html')
def render_uploaded_by_badge(request, topography):
    """Returns a HMTL snippet with a badge about who uploaded a given topography.
    """
    return {
        'topography': topography,
        'is_creator': request.user == topography.creator
    }


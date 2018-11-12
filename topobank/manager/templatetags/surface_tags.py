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

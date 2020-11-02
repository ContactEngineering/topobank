from django import template

register = template.Library()

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


@register.inclusion_tag('manager/published_by_badge.html')
def render_published_by_badge(request, surface):
    """Returns a HMTL snippet with a badge about who published a given surface.
    """
    return {
        'surface': surface,
        'is_publisher': request.user == surface.publication.publisher
    }


@register.inclusion_tag('manager/uploaded_by_badge.html')
def render_uploaded_by_badge(request, topography):
    """Returns a HMTL snippet with a badge about who uploaded a given topography.
    """
    return {
        'topography': topography,
        'is_creator': request.user == topography.creator
    }


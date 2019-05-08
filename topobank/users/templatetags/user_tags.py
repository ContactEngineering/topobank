from django import template

register = template.Library()

@register.inclusion_tag('users/user_label.html')
def render_user_label(user):
    """Returns a HMTL snippet which can be inserted for user representation.
    """
    return {
        'user': user
    }

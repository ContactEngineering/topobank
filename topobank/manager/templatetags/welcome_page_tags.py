from django import template
register = template.Library()


@register.simple_tag
def column_div_class(user_is_anonymous):
    if user_is_anonymous:
        return "col-xl-3 col-sm-6 mb-3"
    else:
        return "col-xl-3 col-sm-6 mb-3"

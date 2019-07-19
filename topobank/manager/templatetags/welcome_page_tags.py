from django import template
register = template.Library()

@register.simple_tag
def column_div_class(user_is_authenticated):
    if user_is_authenticated:
        return "col-xl-3 col-sm-6 mb-3"
    else:
        return "col-xl-3 col-sm-6 mb-3"

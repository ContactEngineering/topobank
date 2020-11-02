from django import template
register = template.Library()


@register.simple_tag
def citation(publication, flavor, request):
    return publication.get_citation(flavor, request)

from django import template
from django.urls import reverse

register = template.Library()

@register.filter
def analyses_results_urls_list_str(analyses):
    l = [ '"'+reverse('analysis:retrieve', kwargs=dict(pk=a.id))+'"' for a in analyses ]
    return '['+','.join(l)+']'

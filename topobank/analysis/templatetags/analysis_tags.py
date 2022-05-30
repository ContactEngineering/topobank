import sys

from django import template
from django.urls import reverse

from ..models import Analysis

register = template.Library()


@register.filter
def analyses_results_urls_list_str(analyses):
    l = ['"'+reverse('analysis:retrieve', kwargs=dict(pk=a.id))+'"' for a in analyses]
    return '['+','.join(l)+']'


@register.filter
def analyses_results_ids_list_str(analyses):
    l = ['{}'.format(a.id) for a in analyses]
    return ','.join(l)


@register.simple_tag
def body_for_mailto_link(analysis, user):

    body = ("Hey there,\n\n"
            "I've problems doing an analysis with 'contact.engineering'.\nHere are some details:\n\n"
            f"Analysis ID: {analysis.id}\n"
            f"Analysis Function: '{analysis.function.name}'\n"
            f"Subject Type: {analysis.subject_type.name}\n"
            f"Subject ID: {analysis.subject.id}\n"
            f"Analysis State: {analysis.get_task_state_display()}\n")

    # using multi line strings was difficult here with the line breaks.

    if analysis.task_state == Analysis.FAILURE:
        r = analysis.result

        try:
            if r['is_incompatible']:
                body += "The topography seems to be incompatible for this kind of analysis.\n"

            body += f"Error message: {r['message']}\n"

            body += "-"*72+"\n"
            body += f"\n{r['traceback']}\n"
            body += "-"*72+"\n"
        except KeyError:
            body += "(Please copy/paste error messages into this mail.)\n"

    body += f"\n\nBest, {user.name}"

    # change characters to we can use this in a link
    body = body.replace('\n', '%0D%0A')
    return body

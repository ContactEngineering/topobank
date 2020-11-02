from django.shortcuts import redirect, Http404

from trackstats.models import Metric, Period

from ..usage_stats.utils import increase_statistics_by_date_and_object
from .models import Publication


def go(request, short_url):
    try:
        pub = Publication.objects.get(short_url=short_url)
    except Publication.DoesNotExist:
        raise Http404()

    increase_statistics_by_date_and_object(Metric.objects.PUBLICATION_VIEW_COUNT,
                                           period=Period.DAY, obj=pub)
    return redirect(pub.surface.get_absolute_url())

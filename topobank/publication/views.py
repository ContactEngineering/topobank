from django.shortcuts import redirect, Http404

from rest_framework import mixins, viewsets

from trackstats.models import Metric, Period

from ..usage_stats.utils import increase_statistics_by_date_and_object
from ..manager.views import download_surface

from .models import Publication
from .serializers import PublicationSerializer


class PublicationViewSet(mixins.RetrieveModelMixin,
                         viewsets.GenericViewSet):
    serializer_class = PublicationSerializer


def go(request, short_url):
    """Visit a published surface by short url."""
    try:
        pub = Publication.objects.get(short_url=short_url)
    except Publication.DoesNotExist:
        raise Http404()

    increase_statistics_by_date_and_object(Metric.objects.PUBLICATION_VIEW_COUNT,
                                           period=Period.DAY, obj=pub)
    return redirect(pub.surface.get_absolute_url())


def download(request, short_url):
    """Download a published surface by short url."""
    try:
        pub = Publication.objects.get(short_url=short_url)
    except Publication.DoesNotExist:
        raise Http404()

    return download_surface(request, pub.surface_id)

import logging

from django.conf import settings
from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView, FormView

from guardian.decorators import permission_required_or_403

from rest_framework import mixins, viewsets

from trackstats.models import Metric, Period

from ..manager.views import download_surface

from .models import Publication
from .serializers import PublicationSerializer

from ..usage_stats.utils import increase_statistics_by_date_and_object
from ..publication.models import MAX_LEN_AUTHORS_FIELD
from ..publication.forms import SurfacePublishForm

from ..manager.models import Surface, NewPublicationTooFastException, PublicationException

_log = logging.getLogger(__name__)

surface_publish_permission_required = method_decorator(
    permission_required_or_403('manager.publish_surface', ('manager.Surface', 'pk', 'pk'))
)

class PublicationViewSet(mixins.ListModelMixin,
                         mixins.RetrieveModelMixin,
                         viewsets.GenericViewSet):
    serializer_class = PublicationSerializer

    # FIXME! This view needs pagination

    def get_queryset(self):
        try:
            original_surface = int(self.request.query_params.get('original_surface', default=None))
            return Publication.objects.filter(original_surface=original_surface).order_by('-version')
        except TypeError:
            return Publication.objects.all()


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


class SurfacePublishView(FormView):
    template_name = "publication/surface_publish.html"
    form_class = SurfacePublishForm

    @surface_publish_permission_required
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, *kwargs)

    def _get_surface(self):
        surface_pk = self.kwargs['pk']
        return Surface.objects.get(pk=surface_pk)

    def get_initial(self):
        initial = super().get_initial()
        initial['author_0'] = ''
        initial['num_author_fields'] = 1
        return initial

    # def get_form_kwargs(self):
    #     kwargs = super().get_form_kwargs()
    #     if self.request.method == 'POST':
    #         # The field 'num_author_fields' may have been increased by
    #         # Javascript (Vuejs) on the client in order to add new authors.
    #         # This should be sent to the form in order to know
    #         # how many fields the form should have and how many author names
    #         # should be combined. So this is passed here:
    #         kwargs['num_author_fields'] = int(self.request.POST.get('num_author_fields'))
    #     return kwargs

    def get_success_url(self):
        return f"{reverse('manager:surface-detail')}?surface={self.kwargs['pk']}"

    def form_valid(self, form):
        license = form.cleaned_data.get('license')
        authors = form.cleaned_data.get('authors_json')
        surface = self._get_surface()
        try:
            surface.publish(license, authors)
        except NewPublicationTooFastException as exc:
            return redirect("publication:surface-publication-rate-too-high",
                            pk=surface.pk)
        except PublicationException as exc:
            msg = f"Publication failed, reason: {exc}"
            _log.error(msg)
            messages.error(self.request, msg)
            return redirect("publication:surface-publication-error",
                            pk=surface.pk)

        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        surface = self._get_surface()

        context['extra_tabs'] = [
            {
                'title': f"{surface.label}",
                'icon': "gem",
                'icon_style_prefix': 'far',
                'href': f"{reverse('manager:surface-detail')}?surface={surface.pk}",
                'active': False,
                'tooltip': f"Properties of surface '{surface.label}'"
            },
            {
                'title': f"Publish surface?",
                'icon': "bullhorn",
                'href': self.request.path,
                'active': True,
                'tooltip': f"Publishing surface '{surface.label}'"
            }
        ]
        context['surface'] = surface
        context['max_len_authors_field'] = MAX_LEN_AUTHORS_FIELD
        user = self.request.user
        context['user_dict'] = dict(
            first_name=user.first_name,
            last_name=user.last_name,
            orcid_id=user.orcid_id
        )
        context['configured_for_doi_generation'] = settings.PUBLICATION_DOI_MANDATORY
        return context


class PublicationRateTooHighView(TemplateView):
    template_name = "publication/publication_rate_too_high.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['min_seconds'] = settings.MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS

        surface_pk = self.kwargs['pk']
        surface = Surface.objects.get(pk=surface_pk)

        context['extra_tabs'] = [
            {
                'title': f"{surface.label}",
                'icon': "gem",
                'icon_style_prefix': 'far',
                'href': f"{reverse('manager:surface-detail')}?surface={surface.pk}",
                'active': False,
                'tooltip': f"Properties of surface '{surface.label}'"
            },
            {
                'title': f"Publication rate too high",
                'icon': "flash",
                'href': self.request.path,
                'active': True,
            }
        ]
        return context


class PublicationErrorView(TemplateView):
    template_name = "publication/publication_error.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        surface_pk = self.kwargs['pk']
        surface = Surface.objects.get(pk=surface_pk)

        context['extra_tabs'] = [
            {
                'title': f"{surface.label}",
                'icon': "gem",
                'icon_style_prefix': 'far',
                'href': f"{reverse('manager:surface-detail')}?surface={surface.pk}",
                'active': False,
                'tooltip': f"Properties of surface '{surface.label}'"
            },
            {
                'title': f"Publication error",
                'icon': "flash",
                'href': self.request.path,
                'active': True,
            }
        ]
        return context

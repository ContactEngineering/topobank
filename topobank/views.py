from django.views.generic import TemplateView
from django.db.models import Q, F

from guardian.compat import get_user_model as guardian_user_model
from guardian.shortcuts import get_objects_for_user, get_perms_for_model

import json

from termsandconditions.models import TermsAndConditions
from topobank.users.models import User
from topobank.manager.models import Surface, Topography
from topobank.manager.utils import selected_instances, selection_choices
from topobank.analysis.models import Analysis

class HomeView(TemplateView):

    template_name = 'pages/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data()

        if self.request.user.is_authenticated:
            user = self.request.user
            surfaces = Surface.objects.filter(creator=user)
            topographies = Topography.objects.filter(surface__in=surfaces)
            analyses = Analysis.objects.filter(topography__in=topographies)
            context['num_surfaces'] = surfaces.count()
            context['num_topographies'] = topographies.count()
            context['num_analyses'] = analyses.count()
            # count surfaces you can view, but you are not creator
            context['num_shared_surfaces'] = get_objects_for_user(user, 'view_surface', klass=Surface)\
                                                .filter(~Q(creator=user)).count()
        else:
            anon = guardian_user_model().get_anonymous()
            context['num_users'] = User.objects.filter(Q(is_active=True) & ~Q(pk=anon.pk)).count()
            context['num_surfaces'] = Surface.objects.filter().count()
            context['num_topographies'] = Topography.objects.filter().count()
            context['num_analyses'] = Analysis.objects.filter().count()

        return context

class TermsView(TemplateView):

    template_name = 'pages/termsconditions.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data()

        active_terms = TermsAndConditions.get_active_terms_list()

        if self.request.user.is_authenticated:
            context['agreed_terms'] = TermsAndConditions.objects.filter(
                    userterms__date_accepted__isnull=False,
                    userterms__user=self.request.user).order_by('optional')

            context['not_agreed_terms'] = active_terms.filter(
                Q(userterms=None) | \
                (Q(userterms__date_accepted__isnull=True) & Q(userterms__user=self.request.user)))\
                .order_by('optional')
        else:
            context['active_terms'] = active_terms.order_by('optional')

        return context

class WorkbenchView(TemplateView):
    template_name = 'pages/workbench.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data()

        selected_topos, selected_surfaces = selected_instances(self.request)
        selected = [{'name': x.name, 'type': 'topography', 'id': x.id} for x in selected_topos]
        selected.extend([{'name': x.name, 'type': 'surface', 'id': x.id} for x in selected_surfaces])

        context['selected_json'] = json.dumps(selected)
        context['choices'] = selection_choices(self.request.user)

        return context

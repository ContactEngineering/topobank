from django.views.generic import TemplateView
from django.db.models import Q

from termsandconditions.models import TermsAndConditions
from topobank.users.models import User
from topobank.manager.models import Surface, Topography

class HomeView(TemplateView):

    template_name = 'pages/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data()

        if self.request.user.is_authenticated:
            user = self.request.user
            surfaces = Surface.objects.filter(user=user)
            topographies_count = Topography.objects.filter(surface__in=surfaces).count()
            context['num_surfaces'] = surfaces.count()
            context['num_topographies'] = topographies_count
        else:
            context['num_users'] = User.objects.filter(is_active=True).count()
            context['num_surfaces'] = Surface.objects.filter().count()
            context['num_topographies'] = Topography.objects.filter().count()

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


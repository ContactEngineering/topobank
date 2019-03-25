from django.views.generic import TemplateView
from django.db.models import Q

from termsandconditions.models import UserTermsAndConditions, TermsAndConditions

class TermsView(TemplateView):

    template_name = 'pages/termsconditions.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['agreed_terms'] = TermsAndConditions.objects.filter(
                userterms__date_accepted__isnull=False,
                userterms__user=self.request.user).order_by('optional')

        active_terms = TermsAndConditions.get_active_terms_list()

        context['not_agreed_terms'] = active_terms.filter(Q(userterms=None) | Q(userterms__date_accepted__isnull=True))\
                                        .order_by('optional')
        return context

from django.views.generic import TemplateView, RedirectView
from django.db.models import Q
from django.shortcuts import reverse
from html import unescape

from guardian.compat import get_user_model as guardian_user_model
from guardian.shortcuts import get_objects_for_user

from termsandconditions.models import TermsAndConditions
from termsandconditions.views import TermsView as OrigTermsView, AcceptTermsView

from topobank.users.models import User
from topobank.manager.models import Surface
from topobank.manager.utils import get_reader_infos
from topobank.usage_stats.utils import current_statistics

class HomeView(TemplateView):

    template_name = 'pages/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        user = self.request.user
        if user.is_anonymous:
            anon = guardian_user_model().get_anonymous()
            context['num_users'] = User.objects.filter(Q(is_active=True) & ~Q(pk=anon.pk)).count()

            current_stats = current_statistics()
        else:
            current_stats = current_statistics(user)

            # count surfaces you can view, but you are not creator
            context['num_shared_surfaces'] = get_objects_for_user(user, 'view_surface', klass=Surface) \
                .filter(~Q(creator=user)).count()

        context['num_surfaces'] = current_stats['num_surfaces_excluding_publications']
        context['num_topographies'] = current_stats['num_topographies_excluding_publications']
        context['num_analyses'] = current_stats['num_analyses_excluding_publications']

        return context


class TermsView(TemplateView):

    template_name = 'pages/termsconditions.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        active_terms = TermsAndConditions.get_active_terms_list()

        if not self.request.user.is_anonymous:
            context['agreed_terms'] = TermsAndConditions.objects.filter(
                    userterms__date_accepted__isnull=False,
                    userterms__user=self.request.user).order_by('optional')

            context['not_agreed_terms'] = active_terms.filter(
                Q(userterms=None) | \
                (Q(userterms__date_accepted__isnull=True) & Q(userterms__user=self.request.user)))\
                .order_by('optional')
        else:
            context['active_terms'] = active_terms.order_by('optional')

        context['extra_tabs'] = [{
            'login_required': False,
            'icon': 'legal',
            'title': "Terms and Conditions",
            'active': True,
        }]

        return context


class HelpView(TemplateView):

    template_name = 'pages/help.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['reader_infos'] = get_reader_infos()
        context['extra_tabs'] = [
            {
                'icon': 'question-circle',
                'title': "Help",
                'href': self.request.path,
                'active': True,
                'login_required': False,
            }
        ]
        return context


class GotoSelectView(RedirectView):
    pattern_name = 'manager:select'
    query_string = True


#
# The following two views are overwritten from
# termsandconditions package in order to add context
# for the tabbed interface
#
def tabs_for_terms(terms, request_path):
    if len(terms) == 1:
        tab_title = unescape(f"{terms[0].name} {terms[0].version_number}")  # mimics '|safe' as in original template
    else:
        tab_title = "Terms"  # should not happen in Topobank, but just to be safe

    return [
        {
            'icon': 'legal',
            'title': "Terms and Conditions",
            'href': reverse('terms'),
            'active': False,
            'login_required': False,
        },
        {
            'icon': 'legal',
            'title': tab_title,
            'href': request_path,
            'active': True,
            'login_required': False,
        }
    ]


class TabbedTermsMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['extra_tabs'] = tabs_for_terms(self.get_terms(self.kwargs), self.request.path)
        return context


class TermsDetailView(TabbedTermsMixin, OrigTermsView):
    pass


class TermsAcceptView(TabbedTermsMixin, AcceptTermsView):
    pass

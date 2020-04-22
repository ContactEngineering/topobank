from django.views.generic import TemplateView, RedirectView
from django.db.models import Q
from django.shortcuts import reverse

from guardian.compat import get_user_model as guardian_user_model
from guardian.shortcuts import get_objects_for_user

from allauth.socialaccount.providers.orcid.provider import OrcidProvider

from termsandconditions.models import TermsAndConditions

from topobank.users.models import User
from topobank.manager.models import Surface, Topography
from topobank.analysis.models import Analysis
from topobank.manager.utils import get_reader_infos

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
            context['surfaces_link'] = reverse('manager:select')
            context['analyses_link'] = reverse('analysis:list')
        else:
            anon = guardian_user_model().get_anonymous()
            context['num_users'] = User.objects.filter(Q(is_active=True) & ~Q(pk=anon.pk)).count()
            context['num_surfaces'] = Surface.objects.filter().count()
            context['num_topographies'] = Topography.objects.filter().count()
            context['num_analyses'] = Analysis.objects.filter().count()

            # The following is a workaround in order to skip the intermediate
            # login page when clicking on 'surfaces' when not logged in.
            # There is an GH issue to solve this in allauth,
            # but it's unlikely that we can use it in foreseeable future:
            #  https://github.com/pennersr/django-allauth/issues/345
            #
            # This is only implemented specifically for ORCID so far.
            # One could look for the actually used providers,
            # but this can be done later if there are any others

            provider = OrcidProvider(self.request)

            def get_login_link(next_url_name):
                return provider.get_login_url(self.request,
                                              method='oauth2',
                                              next=reverse(next_url_name))

            context['surfaces_link'] = get_login_link('manager:select')
            context['analyses_link'] = get_login_link('analysis:list')

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

        context['active_tab'] = 'extra-tab-4'
        context['extra_tab_4_data'] = {
            'icon': 'fa-legal',
            'title': "Terms and Conditions",
            'href': self.request.path,
        }

        return context

class HelpView(TemplateView):

    template_name = 'pages/help.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['reader_infos'] = get_reader_infos()
        context['active_tab'] = 'extra-tab-4'
        context['extra_tab_4_data'] = {
            'icon': 'fa-question-circle',
            'title': "Help",
            'href': self.request.path,
        }
        return context


class GotoSelectView(RedirectView):
    pattern_name = 'manager:select'
    query_string = True


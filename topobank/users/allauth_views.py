# Views that are only required when allauth is configured

from django.urls import reverse

from allauth.account.views import EmailView


class TabbedEmailView(EmailView):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['extra_tabs'] = [
            {
                'title': "User profile",
                'icon': "user",
                'href': reverse('users:detail', kwargs=dict(username=self.request.user.username)),
                'active': False
            },
            {
                'title': "Edit e-mail addresses",
                'icon': "edit",
                'href': self.request.path,
                'active': True
            }
        ]
        return context

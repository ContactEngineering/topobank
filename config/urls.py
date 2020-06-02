from django.conf import settings
from django.urls import include, path
from django.conf.urls.static import static
from django.conf.urls import url
from django.contrib import admin
from django.views.generic import TemplateView
from django.views import defaults as default_views
import notifications.urls

from topobank.views import TermsView, HomeView, HelpView, GotoSelectView, TermsDetailView, TermsAcceptView
from topobank.users.views import TabbedEmailView

urlpatterns = [
                  path("", HomeView.as_view(), name="home"),
                  path(
                      "about/",
                      TemplateView.as_view(template_name="pages/about.html"),
                      name="about",
                  ),
                  path(
                      "termsandconditions/",
                      TermsView.as_view(),
                      name="terms",
                  ),
                  path(
                      "help/",
                      HelpView.as_view(),
                      name="help",
                  ),
                  path(
                      "search/",
                      GotoSelectView.as_view(),
                      name="search",
                  ),
                  # Django Admin, use {% url 'admin:index' %}
                  path(settings.ADMIN_URL, admin.site.urls),
                  # User management
                  path(
                      "users/",
                      include("topobank.users.urls", namespace="users"),
                  ),
                  url("^accounts/email/$", TabbedEmailView.as_view(),
                      name='account_email'),  # same as allauth.accounts.email.EmailView, but with tab data
                  path("accounts/", include("allauth.urls")),

                  # For interactive select boxes
                  url(r'^select2/', include('django_select2.urls')),

                  #
                  # For asking for terms and conditions
                  #

                  # some url specs are overwritten here pointing to own views in order to plug in
                  # some extra context for the tabbed interface
                  # View Specific Active Terms
                  url(r'^terms/view/(?P<slug>[a-zA-Z0-9_.-]+)/$', TermsDetailView.as_view(), name="tc_view_specific_page"),

                  # View Specific Version of Terms
                  url(r'^terms/view/(?P<slug>[a-zA-Z0-9_.-]+)/(?P<version>[0-9.]+)/$', TermsDetailView.as_view(), name="tc_view_specific_version_page"),

                  # Print Specific Version of Terms
                  url(r'^terms/print/(?P<slug>[a-zA-Z0-9_.-]+)/(?P<version>[0-9.]+)/$', TermsDetailView.as_view(template_name="termsandconditions/tc_print_terms.html"), name="tc_print_page"),

                  # Accept Terms
                  url(r'^terms/accept/$', TermsAcceptView.as_view(), name="tc_accept_page"),

                  # Accept Specific Terms
                  url(r'^terms/accept/(?P<slug>[a-zA-Z0-9_.-]+)$', TermsAcceptView.as_view(), name="tc_accept_specific_page"),

                  # Accept Specific Terms Version
                  url(r'^terms/accept/(?P<slug>[a-zA-Z0-9_.-]+)/(?P<version>[0-9\.]+)/$', TermsAcceptView.as_view(), name="tc_accept_specific_version_page"),

                  # the defaults
                  url(r'^terms/', include('termsandconditions.urls')),

                  # progress bar during file upload
                  url(r'^progressbarupload/', include('progressbarupload.urls')),

                  # progress bar for celery tasks
                  url(r'^celery-progress/', include('celery_progress.urls')),

                  # for notifications - see package djano-notifications
                  url('^inbox/notifications/', include(notifications.urls, namespace='notifications')),
                  # Your stuff: custom urls includes go here
                  path(
                      "manager/",
                      include("topobank.manager.urls", namespace="manager"),
                  ),
                  path(
                      "analysis/",
                      include("topobank.analysis.urls", namespace="analysis"),
                  ),
              ] + static(
    settings.MEDIA_URL, document_root=settings.MEDIA_ROOT
)

if settings.DEBUG:
    # This allows the error pages to be debugged during development, just visit
    # these url in browser to see how these error pages look like.
    urlpatterns += [
        path(
            "400/",
            default_views.bad_request,
            kwargs={"exception": Exception("Bad Request!")},
        ),
        path(
            "403/",
            default_views.permission_denied,
            kwargs={"exception": Exception("Permission Denied")},
        ),
        path(
            "404/",
            default_views.page_not_found,
            kwargs={"exception": Exception("Page not Found")},
        ),
        path("500/", default_views.server_error),
    ]
    if "debug_toolbar" in settings.INSTALLED_APPS:
        import debug_toolbar

        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns

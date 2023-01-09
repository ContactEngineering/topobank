import importlib.util

from django.conf import settings
from django.urls import include, path, re_path
from django.conf.urls.static import static
from django.contrib import admin
from django.views.generic import TemplateView, RedirectView
from django.views import defaults as default_views
from django.apps import apps
from django.contrib.auth.decorators import user_passes_test, login_required
from django.http import HttpResponse

import notifications.urls

from topobank.views import TermsView, HomeView, HelpView, GotoSelectView, TermsDetailView, TermsAcceptView
from topobank.users.views import TabbedEmailView
from topobank.organizations.models import Organization

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
                  re_path("^accounts/email/$", TabbedEmailView.as_view(),
                      name='account_email'),  # same as allauth.accounts.email.EmailView, but with tab data
                  path("accounts/", include("allauth.urls")),

                  # For interactive select boxes
                  re_path(r'^select2/', include('django_select2.urls')),

                  #
                  # For asking for terms and conditions
                  #

                  # some url specs are overwritten here pointing to own views in order to plug in
                  # some extra context for the tabbed interface
                  # View Specific Active Terms
                  re_path(r'^terms/view/(?P<slug>[a-zA-Z0-9_.-]+)/$', TermsDetailView.as_view(), name="tc_view_specific_page"),

                  # View Specific Version of Terms
                  re_path(r'^terms/view/(?P<slug>[a-zA-Z0-9_.-]+)/(?P<version>[0-9.]+)/$', TermsDetailView.as_view(), name="tc_view_specific_version_page"),

                  # Print Specific Version of Terms
                  re_path(r'^terms/print/(?P<slug>[a-zA-Z0-9_.-]+)/(?P<version>[0-9.]+)/$', TermsDetailView.as_view(template_name="termsandconditions/tc_print_terms.html"), name="tc_print_page"),

                  # Accept Terms
                  re_path(r'^terms/accept/$', TermsAcceptView.as_view(), name="tc_accept_page"),

                  # Accept Specific Terms
                  re_path(r'^terms/accept/(?P<slug>[a-zA-Z0-9_.-]+)$', TermsAcceptView.as_view(), name="tc_accept_specific_page"),

                  # Accept Specific Terms Version
                  re_path(r'^terms/accept/(?P<slug>[a-zA-Z0-9_.-]+)/(?P<version>[0-9\.]+)/$', TermsAcceptView.as_view(), name="tc_accept_specific_version_page"),

                  # the defaults
                  re_path(r'^terms/', include('termsandconditions.urls')),

                  # progress bar during file upload
                  re_path(r'^progressbarupload/', include('progressbarupload.urls')),

                  # progress bar for celery tasks
                  re_path(r'^celery-progress/', include('celery_progress.urls')),

                  # for notifications - see package djano-notifications
                  re_path('^inbox/notifications/', include(notifications.urls, namespace='notifications')),
                  # Your stuff: custom urls includes go here
                  path(
                      "manager/",
                      include("topobank.manager.urls", namespace="manager"),
                  ),
                  path(
                      "go/",  # shorter than 'publication'
                      include("topobank.publication.urls", namespace="publication"),
                  ),
                  path(
                      "analysis/",
                      include("topobank.analysis.urls", namespace="analysis"),
                  ),
                  path(
                      "plugins/",
                      include("topobank.plugins.urls", namespace="plugins"),
                  ),
                  path(
                      "health-check/",
                      lambda request: HttpResponse("OK", status=200),
                      name='health-check'
                  ),
            ] + static(
                settings.MEDIA_URL, document_root=settings.MEDIA_ROOT
            )

if settings.CHALLENGE_REDIRECT_URL:
    urlpatterns += [
        path(
            "challenge/",
            RedirectView.as_view(url=settings.CHALLENGE_REDIRECT_URL, permanent=False),
            name="challenge",
        ),
    ]

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

#
# Load URL patterns from plugins
#
def plugin_urls(urllist, app_name):
    for entry in urllist:
        if hasattr(entry, 'url_patterns'):
            plugin_urls(entry.url_patterns)
        elif hasattr(entry, 'callback'):
            def plugin_available_check(user):
                return app_name in Organization.objects.get_plugins_available(user)
            callback_decorator = user_passes_test(plugin_available_check, login_url='/403/', redirect_field_name=None)
            entry.callback = callback_decorator(login_required(entry.callback))
    return urllist


plugin_patterns = []
for app in apps.get_app_configs():
    if hasattr(app, 'TopobankPluginMeta'):
        url_module_name = app.name + '.urls'
        if importlib.util.find_spec(url_module_name):
            url_module = importlib.import_module(url_module_name)
            plugin_patterns.append(
                path(
                    f"plugins/{app.name}/",  # all urls of this plugin start with this
                    # Allow access only if plugin available
                    include((plugin_urls(url_module.urlpatterns, app_name=app.name), app.label))
                    # Allow access independent of plugin availability (always permitted)
                    # include((url_module.urlpatterns, app.label))
                )
            )
urlpatterns.extend(plugin_patterns)

# Idea, also by Raphael Michel (Djangocon 2019): Auto-wrap all plugin views in a decorator
#
# Instead of
#   include((url_module.urlpatterns, app.label))
# use
#   include((plugin_urls(url_module.urlpatterns), app.label))
# with
# def plugin_urls(urllist):
#     for entry in urllist:
#         if hasattr((entry, "url_patterns")):
#             plugin_urls(entry.url_patterns)
#         elif hasattr(entry, 'callback'):
#             entry.callback = login_required(entry.callback)
#     return urllist
#
# Or any other decorator, e.g. permission checking


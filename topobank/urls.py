import importlib.util

import notifications.urls
from django.apps import apps
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.decorators import user_passes_test
from django.urls import include, path, re_path
from django.views import defaults as default_views
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from topobank.organizations.models import Organization
from topobank.users.allauth_views import TabbedEmailView

urlpatterns = [
    #
    # User management
    #
    path(
        "users/",
        include("topobank.users.urls", namespace="users"),
    ),
    re_path(
        "^accounts/email/$", TabbedEmailView.as_view(), name="account_email"
    ),  # same as allauth.accounts.email.EmailView, but with tab data
    path("accounts/", include("allauth.urls")),
    #
    # Core topobank applications
    #
    path(
        "manager/",
        include("topobank.manager.urls", namespace="manager"),
    ),
    path(
        "analysis/",
        include("topobank.analysis.urls", namespace="analysis"),
    ),
    path(
        "plugins/",
        include("topobank.plugins.urls", namespace="plugins"),
    ),
    #
    # Django Admin, use {% url 'admin:index' %}
    #
    path(settings.ADMIN_URL, admin.site.urls),
    #
    # Notifications - see package django-notifications
    #
    re_path(
        "^inbox/notifications/", include(notifications.urls, namespace="notifications")
    ),
    #
    # Watchman - see package django-watchman
    #
    path("watchman/", include(("watchman.urls", "watchman"), namespace="watchman")),
    #
    # Open Api
    #
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]

#
# Add serving of static files
#
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

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
def plugin_urls(urllist, app):
    for entry in urllist:
        if hasattr(entry, "url_patterns"):
            # This is a list of URL patterns
            entry.url_patterns = plugin_urls(entry.url_patterns, app)
        elif hasattr(entry, "callback"):
            # This is a path with a view
            def plugin_available_check(user):
                if app.TopobankPluginMeta.restricted:
                    return app.name in Organization.objects.get_plugins_available(user)
                return True

            callback_decorator = user_passes_test(
                plugin_available_check, login_url="/403/", redirect_field_name=None
            )
            entry.callback = callback_decorator(entry.callback)
    return urllist


plugin_patterns = []
for app in apps.get_app_configs():
    if hasattr(app, "TopobankPluginMeta"):
        url_module_name = app.name + ".urls"
        if importlib.util.find_spec(url_module_name):
            url_module = importlib.import_module(url_module_name)
            if hasattr(url_module, "urlprefix") and url_module.urlprefix is not None:
                plugin_patterns.append(
                    path(
                        url_module.urlprefix,  # all urls of this plugin start with this
                        # Allow access only if plugin available
                        include(
                            (plugin_urls(url_module.urlpatterns, app=app), app.label)
                        ),
                        # Allow access independent of plugin availability (always permitted)
                        # include((url_module.urlpatterns, app.label))
                    )
                )
            else:
                # This plugin wants to register top-level routes; this is usually the user-interface plugin
                plugin_patterns.extend(
                    # Allow access only if plugin available
                    plugin_urls(url_module.urlpatterns, app=app)
                    # Allow access independent of plugin availability (always permitted)
                    # include((url_module.urlpatterns, app.label))
                )

urlpatterns.extend(plugin_patterns)

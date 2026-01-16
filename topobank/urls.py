import importlib.util

import notifications.urls
from django.apps import apps
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.decorators import user_passes_test
from django.contrib.staticfiles import views as static_views
from django.urls import include, path, re_path
from django.views import defaults as default_views
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .organizations.models import Organization
from .views import entry_points

urlpatterns = [
    #
    # Entry points
    #
    path("entry-points/", entry_points),
    #
    # User management
    #
    path(
        "users/",
        include("topobank.users.urls", namespace="users"),
    ),
    #
    # Organization management
    #
    path(
        "organizations/",
        include("topobank.organizations.urls", namespace="organizations"),
    ),
    #
    # Permission management
    #
    path(
        "authorization/",
        include("topobank.authorization.urls", namespace="authorization"),
    ),
    #
    # Core topobank applications
    #
    path(
        "files/",
        include("topobank.files.urls", namespace="files"),
    ),
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
    # Note: plugin's may provided optimized wrapper views that take precedence
    #
    re_path(
        "^inbox/notifications/", include(notifications.urls, namespace="notifications")
    ),
    #
    # Watchman - see package django-watchman
    # Note: plugin's may provided optimized wrapper views that take precedence
    #
    path("watchman/", include(("watchman.urls", "watchman"), namespace="watchman")),
    #
    # Open API
    #
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
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
        re_path(r"^static/(?P<path>.*)$", static_views.serve),
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

# Plugin URLs are prepended to allow plugins to override default routes
# This is important! It allows plugins to provide optimized versions
# of infrastructure endpoints (e.g., watchman, notifications with @transaction.non_atomic_requests)
urlpatterns = plugin_patterns + urlpatterns

from .base import *  # noqa
from .base import env

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
SECRET_KEY = env("DJANGO_SECRET_KEY", default=random_string())  # noqa: F405
# https://docs.djangoproject.com/en/dev/ref/settings/#allowed-hosts
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["example.com"])

# DATABASES
# ------------------------------------------------------------------------------
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)  # noqa F405

# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-proxy-ssl-header
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-ssl-redirect
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-secure
SESSION_COOKIE_SECURE = True
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-httponly
SESSION_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-secure
CSRF_COOKIE_SECURE = True
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-httponly
CSRF_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/topics/security/#ssl-https
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-seconds
# TODO: set this to 60 seconds first and then to 518400 once you prove the former works
SECURE_HSTS_SECONDS = 60
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-include-subdomains
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True
)
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-preload
SECURE_HSTS_PRELOAD = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=True)
# https://docs.djangoproject.com/en/dev/ref/middleware/#x-content-type-options-nosniff
SECURE_CONTENT_TYPE_NOSNIFF = env.bool(
    "DJANGO_SECURE_CONTENT_TYPE_NOSNIFF", default=True
)
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-browser-xss-filter
SECURE_BROWSER_XSS_FILTER = True
# https://docs.djangoproject.com/en/dev/ref/settings/#x-frame-options
X_FRAME_OPTIONS = "DENY"

# TEMPLATES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#templates
TEMPLATES[0]["OPTIONS"]["loaders"] = [  # noqa F405
    (
        "django.template.loaders.cached.Loader",
        [
            "django.template.loaders.filesystem.Loader",
            "django.template.loaders.app_directories.Loader",
        ],
    ),
]

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#default-from-email
DEFAULT_FROM_EMAIL = env(
    "DJANGO_DEFAULT_FROM_EMAIL",
    default="contact.engineering <noreply@contact.engineering>",
)
# https://docs.djangoproject.com/en/dev/ref/settings/#server-email
SERVER_EMAIL = env("DJANGO_SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)
# https://docs.djangoproject.com/en/dev/ref/settings/#email-subject-prefix
EMAIL_SUBJECT_PREFIX = env(
    "DJANGO_EMAIL_SUBJECT_PREFIX", default="[contact.engineering]"
)

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL regex.
ADMIN_URL = env("DJANGO_ADMIN_URL", default=random_string())  # noqa: F405

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

EMAIL_CONFIG = env.email_url(
    "DJANGO_EMAIL_URL", default="smtp://user@:password@localhost:25"
)
# For SMTP+SSL use: smtp+ssl://
vars().update(EMAIL_CONFIG)  # this sets all variables needed by Django

# Anymail (Mailgun, PostMark and others)
# ------------------------------------------------------------------------------
# https://anymail.readthedocs.io/en/stable/installation/#installing-anymail
# INSTALLED_APPS += ['anymail']  # noqa F405
# EMAIL_BACKEND = 'anymail.backends.postmark.EmailBackend' # TODO there is also an entry in base.py, also use here?
# ANYMAIL = {
#     "POSTMARK_SERVER_TOKEN": env('POSTMARK_SERVER_TOKEN')
# }
# EMAIL_BACKEND = 'anymail.backends.mailgun.EmailBackend'
#  https://anymail.readthedocs.io/en/stable/installation/#anymail-settings-reference
# ANYMAIL = {
#     'MAILGUN_API_KEY': env('MAILGUN_API_KEY'),
#     'MAILGUN_SENDER_DOMAIN': env('MAILGUN_DOMAIN')
# }

# Gunicorn
# ------------------------------------------------------------------------------
INSTALLED_APPS += ["gunicorn"]  # noqa F405

# LOGGING
# ------------------------------------------------------------------------------
# See: https://docs.djangoproject.com/en/dev/ref/settings/#logging
# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error when DEBUG=False.
# See https://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"require_debug_false": {"()": "django.utils.log.RequireDebugFalse"}},
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s "
            "%(process)d %(thread)d %(message)s"
        },
    },
    "handlers": {
        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "class": "django.utils.log.AdminEmailHandler",
        },
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django.request": {
            "handlers": ["console", "mail_admins"],
            "level": "ERROR",
            "propagate": True,
        },
        "django.security.DisallowedHost": {
            "level": "ERROR",
            "handlers": ["console", "mail_admins"],
            "propagate": True,
        },
        "topobank": {"level": "INFO", "handlers": ["console"], "propagate": True},
        "watchman": {
            "handlers": ["console"],
            "level": "INFO",
        },
    },
}

# Your stuff...
# ------------------------------------------------------------------------------

# Bokeh output backend. Possibilities are:
# - 'canvas': The default
# - 'svg': Render using SVG. Plot will download as SVG if this is enabled while they download as PNG in the 'canvas'
#   backend. SVG has problems with zooming plots.
# - 'webgl': Accelerates some plots using WebGL
BOKEH_OUTPUT_BACKEND = "svg"

# Settings for watchman
# WATCHMAN_AUTH_DECORATOR = 'watchman.decorators.token_required'
WATCHMAN_AUTH_DECORATOR = "django.contrib.admin.views.decorators.staff_member_required"
# like this, you need to login as a staff member (can be achieved using the 'grant_admin_permissions'
# management command) in order to see the dashboard;
# Can also be configured to use a token or no token at all, see
# https://django-watchman.readthedocs.io/en/latest/readme.html#documentation
# for details

# STATIC FILES
# ------------------------------------------------------------------------------
# We use ServeStatic in production for delivering static files. Those files need
# to be collected with `manage.py collectstatic` before. (This happens when
# building the Docker container.) Now we insert `ServeStaticMiddleware` after
# `SecurityMiddleware`.
MIDDLEWARE.insert(  # noqa: F405
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,  # noqa: F405
    "servestatic.middleware.ServeStaticMiddleware",
)

# STORAGE
# ------------------------------------------------------------------------------
USE_S3_STORAGE = True
STORAGES = {
    "default": {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"},
    "staticfiles": {
        "BACKEND": "servestatic.storage.CompressedManifestStaticFilesStorage"
    },
}

# ORCID
# ------------------------------------------------------------------------------
INSTALLED_APPS.insert(
    INSTALLED_APPS.index("allauth.socialaccount") + 1,
    "allauth.socialaccount.providers.orcid",
)

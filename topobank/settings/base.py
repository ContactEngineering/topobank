"""
Base settings to build other settings files upon.
"""

import importlib.metadata
import random
import string
from datetime import timedelta

import environ
from backports.entry_points_selectable import entry_points
from django.core.exceptions import ImproperlyConfigured
from watchman import constants as watchman_constants

import topobank


def random_string(L=16):
    return "".join(random.choice(string.ascii_lowercase) for i in range(L))


# We provide (dummy) default values for every setting so we can run manage.py
# without needing a configured stack.

env = environ.Env()

APPS_DIR = environ.Path(topobank.__file__) - 1

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = env.bool("DJANGO_DEBUG", False)
# Local time zone. Choices are
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# though not all of them may be available with every OS.
# In Windows, this must be set to your system time zone.
TIME_ZONE = "Europe/Berlin"
# https://docs.djangoproject.com/en/dev/ref/settings/#language-code
LANGUAGE_CODE = "en-us"
# https://docs.djangoproject.com/en/dev/ref/settings/#site-id
SITE_ID = 1
# https://docs.djangoproject.com/en/dev/ref/settings/#use-i18n
USE_I18N = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-tz
USE_TZ = True

# DATABASES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#databases
postgres_db = env("POSTGRES_DB", default=None)
if postgres_db is None:
    DATABASES = {"default": env.db("DATABASE_URL", default="postgres:///topobank-test")}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": postgres_db,
            "USER": env("POSTGRES_USER"),
            "PASSWORD": env("POSTGRES_PASSWORD"),
            "HOST": env("POSTGRES_HOST"),
            "PORT": env("POSTGRES_PORT"),
        }
    }
DATABASES["default"]["ATOMIC_REQUESTS"] = True

# URLS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#root-urlconf
ROOT_URLCONF = "topobank.urls"
# https://docs.djangoproject.com/en/dev/ref/settings/#wsgi-application
WSGI_APPLICATION = "topobank.wsgi.application"

# APPS
# ------------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "django.contrib.postgres",  # needed for 'search' lookup
]
THIRD_PARTY_APPS = [
    "allauth",  # authentication
    "allauth.account",
    "allauth.socialaccount",  # social authentication
    "rest_framework",  # REST API
    "storages",  # S3 storage
    "guardian",  # needed for migrations only
    "notifications",
    "tagulous",  # tag-model with hierarchies
    "trackstats",
    "watchman",  # system status report
    "request_profiler",  # keep track of response times for selected routes
    "drf_spectacular",  # API documentation
]
LOCAL_APPS = [
    # Your stuff: custom apps go here
    "topobank.users.apps.UsersAppConfig",
    "topobank.authorization.apps.AuthorizationAppConfig",
    "topobank.files.apps.FilesAppConfig",
    "topobank.manager.apps.ManagerAppConfig",
    "topobank.analysis.apps.AnalysisAppConfig",
    "topobank.usage_stats.apps.UsageStatsAppConfig",
    "topobank.organizations.apps.OrganizationsAppConfig",
    "topobank.properties.apps.PropertiesAppConfig",
]

PLUGIN_MODULES = [
    entry_point.name for entry_point in entry_points(group="topobank.plugins")
]
PLUGIN_APPS = [
    entry_point.value for entry_point in entry_points(group="topobank.plugins")
]
print(f"PLUGIN_MODULES: {PLUGIN_MODULES}")
for mod in PLUGIN_MODULES:
    version = importlib.metadata.version(mod)
    file = importlib.util.find_spec(mod).origin
    print(f"{mod}: {version}, {file}")
print(f"PLUGIN_APPS: {PLUGIN_APPS}")

PLUGIN_THIRD_PARTY_APPS = [
    entry_point.value for entry_point in entry_points(group="topobank.third_party_apps")
]
print(f"PLUGIN_THIRD_PARTY_APPS: {PLUGIN_THIRD_PARTY_APPS}")
THIRD_PARTY_APPS += PLUGIN_THIRD_PARTY_APPS

# https://docs.djangoproject.com/en/dev/ref/settings/#installed-apps
# Remove duplicate entries
INSTALLED_APPS = list(set(DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS + PLUGIN_APPS))

# MIGRATIONS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#migration-modules
MIGRATION_MODULES = {"sites": "topobank.contrib.sites.migrations"}

# AUTO-CREATED PRIMARY KEYS
# ------------------------------------------------------------------------------
# New in Django 3.2.
# See: https://docs.djangoproject.com/en/3.2/releases/3.2/#customizing-type-of-auto-created-primary-keys
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# AUTHENTICATION
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#authentication-backends
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-user-model
AUTH_USER_MODEL = "users.User"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-redirect-url
LOGIN_REDIRECT_URL = "home"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-url
LOGIN_URL = "account_login"

# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = [
    # https://docs.djangoproject.com/en/dev/topics/auth/passwords/#using-argon2-with-django
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.BCryptPasswordHasher",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# MIDDLEWARE
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#middleware
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Request profiler needs to be after authentication middleware to be able to log
    # user info
    "request_profiler.middleware.ProfilingMiddleware",
    # Allauth
    "allauth.account.middleware.AccountMiddleware",
]

PLUGIN_MIDDLEWARE = [
    entry_point.value for entry_point in entry_points(group="topobank.middleware")
]
print(f"PLUGIN_MIDDLEWARE: {PLUGIN_MIDDLEWARE}")

# Plugin middleware must be called before anonymous user replacement, because the UI plugin registers Terms & Conditions
# middleware. If plugin middleware comes last, then anonymous users will always be asked to accept terms and conditions.
MIDDLEWARE += PLUGIN_MIDDLEWARE

MIDDLEWARE += [
    # we need an anonymous user with a user id for API calls
    "topobank.middleware.anonymous_user_middleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

#
# Usage statistics
#
ENABLE_USAGE_STATS = env("TOPOBANK_ENABLE_USAGE_STATS", default=False)

# TEMPLATES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#templates

PLUGIN_CONTEXT_PROCESSORS = [
    entry_point.value
    for entry_point in entry_points(group="topobank.context_processors")
]
print(f"PLUGIN_CONTEXT_PROCESSORS: {PLUGIN_CONTEXT_PROCESSORS}")

TEMPLATES = [
    {
        # https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-TEMPLATES-BACKEND
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # https://docs.djangoproject.com/en/dev/ref/settings/#template-dirs
        # 'APP_DIRS': True,
        "DIRS": [
            str(APPS_DIR.path("templates")),
        ],
        "OPTIONS": {
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-debug
            "debug": DEBUG,
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-loaders
            # https://docs.djangoproject.com/en/dev/ref/templates/api/#loader-types
            "loaders": [
                "django.template.loaders.filesystem.Loader",
                "django.template.loaders.app_directories.Loader",
            ],
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
            ]
            + PLUGIN_CONTEXT_PROCESSORS,
        },
    },
]

# FIXTURES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#fixture-dirs
FIXTURE_DIRS = (str(APPS_DIR.path("fixtures")),)

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"
)

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL.
ADMIN_URL = "admin/"
# https://docs.djangoproject.com/en/dev/ref/settings/#admins
ADMINS = [("""Lars Pastewka""", "lars.pastewka@imtek.uni-freiburg.de")]
# https://docs.djangoproject.com/en/dev/ref/settings/#managers
MANAGERS = ADMINS

# Celery
# ------------------------------------------------------------------------------
INSTALLED_APPS += ["topobank.taskapp.celeryapp.CeleryAppConfig"]
if USE_TZ:
    # http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-timezone
    CELERY_TIMEZONE = TIME_ZONE
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-broker_url
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://redis:6379/0")
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-result_backend
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://127.0.0.1:6379/0")
# we don't use rpc:// as default here, because Python 3.7 is not officially supported by celery 4.2
# and there is a problem with Python 3.7's keyword 'async' which is used in the celery code

CELERY_RESULT_PERSISTENT = True
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-accept_content
CELERY_ACCEPT_CONTENT = ["json"]
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-task_serializer
CELERY_TASK_SERIALIZER = "json"
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-result_serializer
CELERY_RESULT_SERIALIZER = "json"
# TODO: set to whatever value is adequate in your circumstances
# CELERYD_TASK_TIME_LIMIT = 5 * 60
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#task-soft-time-limit
# TODO: set to whatever value is adequate in your circumstances
# CELERYD_TASK_SOFT_TIME_LIMIT = 60
# https://docs.celeryq.dev/en/latest/userguide/configuration.html#task-acks-late
CELERY_TASK_ACKS_LATE = False
# https://docs.celeryq.dev/en/latest/userguide/configuration.html#task-publish-retry
CELERY_TASK_PUBLISH_RETRY = False  # Don'r retry on connection issues
# https://docs.celeryq.dev/en/latest/userguide/configuration.html#task-track-started
CELERY_TASK_TRACK_STARTED = True

TOPOBANK_MANAGER_QUEUE = env.str("MANAGER_QUEUE_NAME", default="manager")
TOPOBANK_ANALYSIS_QUEUE = env.str("ANALYSIS_QUEUE_NAME", default="analysis")

CELERY_TASK_ROUTES = {
    "topobank.analysis.tasks.perform_analysis": {"queue": TOPOBANK_ANALYSIS_QUEUE},
}

# https://docs.celeryproject.org/en/stable/userguide/configuration.html#worker-cancel-long-running-tasks-on-connection-loss
CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS = True
# https://docs.celeryproject.org/en/stable/userguide/configuration.html?highlight=heartbeat#broker-heartbeat
CELERY_BROKER_HEARTBEAT = 60
CELERY_REDIS_BACKEND_HEALTH_CHECK_INTERVAL = 30

# https://docs.celeryq.dev/en/latest/userguide/periodic-tasks.html
CELERY_BEAT_SCHEDULE = {
    "manager": {
        "task": "topobank.manager.custodian.periodic_cleanup",
        "schedule": 12 * 3600,  # Twice a day
    },
    "analysis": {
        "task": "topobank.analysis.custodian.periodic_cleanup",
        "schedule": 12 * 3600,  # Twice a day
    },
}

# django-allauth
# ------------------------------------------------------------------------------
# https://django-allauth.readthedocs.io/en/latest/configuration.html
ACCOUNT_FORMS = {"signup": "topobank.users.forms.SignupFormWithName"}
# ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
ACCOUNT_EMAIL_VERIFICATION = "none"
# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_ADAPTER = "topobank.users.adapters.AccountAdapter"
# https://docs.allauth.org/en/latest/socialaccount/configuration.html
SOCIALACCOUNT_ADAPTER = "topobank.users.adapters.SocialAccountAdapter"
SOCIALACCOUNT_LOGIN_ON_GET = True  # True: disable intermediate page
ACCOUNT_LOGOUT_ON_GET = True  # True: disable intermediate page

#
# Define permissions when using the rest framework
#
# Make sure that no one can retrieve data from other users, e.g. in view. See GH 168.
# This may help: https://www.django-rest-framework.org/api-guide/permissions/
# This seems to fit well: https://www.django-rest-framework.org/tutorial/4-authentication-and-permissions/
#
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": (
        # Anonymous user is not authenticated but needs read-only access
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "topobank",
    "DESCRIPTION": "A surface metrology cloud database",
    "VERSION": topobank.__version__,
    "SERVE_INCLUDE_SCHEMA": False,
    # OTHER SETTINGS
}
#
# Settings for authentication with ORCID
#
SOCIALACCOUNT_PROVIDERS = {
    "orcid": {
        # Base domain of the API. Default value: 'orcid.org', for the production API
        # 'BASE_DOMAIN':'sandbox.orcid.org',  # for the sandbox API
        # Member API or Public API? Default: False (for the public API)
        # 'MEMBER_API': False,  # for the member API
    }
}
SOCIALACCOUNT_QUERY_EMAIL = (
    True  # e-mail should be aquired from social account provider
)


def ACCOUNT_USER_DISPLAY(user):
    return user.name


# Terms and conditions
# ------------------------------------------------------------------------------
TERMS_BASE_TEMPLATE = "pages/termsframe.html"
TERMS_EXCLUDE_URL_LIST = {"/accounts/logout/"}
# TERMS_EXCLUDE_URL_PREFIX_LIST = {'/users/'}
TERMS_EXCLUDE_USERS_WITH_PERM = "users.can_skip_terms"
TERMS_STORE_IP_ADDRESS = False

# S3
# ------------------------------------------------------------------------------
AWS_LOCATION = env.str("AWS_MEDIA_PREFIX", default="media")

AWS_ACCESS_KEY_ID = env.str("AWS_ACCESS_KEY_ID", default=None)
AWS_SECRET_ACCESS_KEY = env.str("AWS_SECRET_ACCESS_KEY", default=None)

AWS_STORAGE_BUCKET_NAME = env.str("AWS_STORAGE_BUCKET_NAME", default="topobank-assets")

AWS_AUTO_CREATE_BUCKET = True

AWS_S3_ENDPOINT_URL = env.str("AWS_S3_ENDPOINT_URL", default=None)
AWS_S3_USE_SSL = env.bool("AWS_S3_USE_SSL", default=True)
AWS_S3_VERIFY = env.bool("AWS_S3_VERIFY", default=True)
AWS_DEFAULT_ACL = None
# Append extra characters if new files have the same name
AWS_S3_FILE_OVERWRITE = False

# STATIC
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT = env.str(
    "DJANGO_STATIC_ROOT", default=(APPS_DIR - 2).path("staticfiles")
)  # This is not used in the development environment
print(f"STATIC_ROOT: {STATIC_ROOT}")
# https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = "/static/"
print(f"STATIC_URL: {STATIC_URL}")
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIR = env.str("DJANGO_STATICFILES_DIR", default=None)
# The /static dir of each app is searched automatically, we here add one auxiliary directory
if STATICFILES_DIR is None:
    STATICFILES_DIRS = []
else:
    STATICFILES_DIRS = [STATICFILES_DIR]
print(f"STATICFILES_DIRS: {STATICFILES_DIRS}")

# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#staticfiles-finders
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

# MEDIA
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#media-root
MEDIA_ROOT = ""
# https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = "/media/"

#
# Settings for tracking package versions for analyses
#
# list of tuples of form (import_name, expression_returning_version_string)
TRACKED_DEPENDENCIES = [
    (
        "topobank",
        "topobank.__version__",
        "MIT",
        "https://github.com/ContactEngineering/topobank",
    )
]

# Extend tracked dependencies by Plugin apps
for plugin_module, plugin_app in zip(PLUGIN_MODULES, PLUGIN_APPS):
    TRACKED_DEPENDENCIES.append(
        (
            plugin_module,
            plugin_app + ".TopobankPluginMeta.version",
            "MIT",
            f"https://github.com/ContactEngineering/{plugin_module}",
        )
    )

TRACKED_DEPENDENCIES += [
    (
        "SurfaceTopography",
        "SurfaceTopography.__version__",
        "MIT",
        "https://github.com/ContactEngineering/SurfaceTopography",
    ),
    ("NuMPI", "NuMPI.__version__", "MIT", "https://github.com/IMTEK-Simulation/NuMPI"),
    ("muFFT", "muFFT.__version__", "LGPL-3.0", "https://github.com/muSpectre/muFFT"),
    ("numpy", "numpy.__version__", "BSD 3-Clause", "https://numpy.org/"),
    ("scipy", "scipy.__version__", "BSD 3-Clause", "https://scipy.org/"),
    ("pandas", "pandas.__version__", "BSD 3-Clause", "https://pandas.pydata.org/"),
    (
        "xarray",
        "xarray.__version__",
        "BSD 3-Clause",
        "https://xarray.pydata.org/en/stable/",
    ),
    ("django", "django.__version__", "BSD 3-Clause", "https://www.djangoproject.com/"),
    (
        "allauth",
        "allauth.__version__",
        "BSD 3-Clause",
        "https://django-allauth.readthedocs.io/en/latest/",
    ),
    (
        "storages",
        "storages.__version__",
        "BSD 3-Clause",
        "https://django-storages.readthedocs.io/en/latest/",
    ),
    (
        "boto3",
        "boto3.__version__",
        "Apache 2.0",
        "https://boto3.amazonaws.com/v1/documentation/api/latest/index.html",
    ),
    (
        "rest_framework",
        "rest_framework.__version__",
        "BSD 3-Clause",
        "https://www.django-rest-framework.org/",
    ),
]

#
# Settings for notifications package
#
DJANGO_NOTIFICATIONS_CONFIG = {"USE_JSONFIELD": True}
# I would like to pass the target url to a notification

#
# Settings for django-tagulous (tagging)
#
SERIALIZATION_MODULES = {
    "xml": "tagulous.serializers.xml_serializer",
    "json": "tagulous.serializers.json",
    "python": "tagulous.serializers.python",
    "yaml": "tagulous.serializers.pyyaml",
}

# TAGULOUS_AUTOCOMPLETE_JS = (
#    "tagulous/lib/select2-4/js/select2.full.min.js",
#    "tagulous/tagulous.js",
#    "tagulous/adaptor/select2-4.js",
# )

#
# E-Mail address to contact us
#
CONTACT_EMAIL_ADDRESS = "support@contact.engineering"

#
# Publication and Datacite settings (DOI creation)
#

# set to None to disable check
MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS = env.int(
    "MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS", 600
)

CC_LICENSE_INFOS = {  # each element refers to two links: (description URL, full license text URL)
    "cc0-1.0": {
        "description_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "legal_code_url": "https://creativecommons.org/publicdomain/zero/1.0/legalcode",
        "title": "CC0 1.0 Universal",
        "option_name": "CC0 1.0 (Public Domain Dedication)",
        "spdx_identifier": "CC0-1.0",
    },
    "ccby-4.0": {
        "description_url": "https://creativecommons.org/licenses/by/4.0/",
        "legal_code_url": "https://creativecommons.org/licenses/by/4.0/legalcode",
        "title": "Creative Commons Attribution 4.0 International Public License",
        "option_name": "CC BY 4.0",
        "spdx_identifier": "CC-BY-4.0",
    },
    "ccbysa-4.0": {
        "description_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "legal_code_url": "https://creativecommons.org/licenses/by-sa/4.0/legalcode",
        "title": "Creative Commons Attribution-ShareAlike 4.0 International Public License",
        "option_name": "CC BY-SA 4.0",
        "spdx_identifier": "CC-BY-SA-4.0",
    },
}
# For SPDX identifiers, see https://spdx.org/licenses/
# It may be useful to use these identifiers also everywhere in the code when identifying a license,
# but then we also need to change the existing entries in the database.

# Set the following to False, if publications shouldn't be possible at all
PUBLICATION_ENABLED = env.bool("PUBLICATION_ENABLED", default=True)

PUBLICATION_DOI_STATE_INFOS = {
    "draft": {
        "description": "only visible in Fabrica, DOI can be deleted",
    },
    "registered": {
        "description": "registered with the DOI Resolver, cannot be deleted",
    },
    "findable": {
        "description": "registered with the DOI Resolver and indexed in DataCite Search, cannot be deleted",
    },
}

# Prefix of the URL each DOI refers to, the short url of the publication is added
PUBLICATION_URL_PREFIX = env.str(
    "PUBLICATION_URL_PREFIX", "https://contact.engineering/go/"
)

# Set this to True if each publication must get a DOI on creation
PUBLICATION_DOI_MANDATORY = env.bool("PUBLICATION_DOI_MANDATORY", default=False)

# Prefix of the DOI to be generated, e.g. '10.82035'
PUBLICATION_DOI_PREFIX = env.str(
    "PUBLICATION_DOI_PREFIX", "99.999"
)  # 99.999 is invalid, should start with '10.'

# These are the credentials for DataCite
DATACITE_USERNAME = env.str("DATACITE_USERNAME", default=random_string())
DATACITE_PASSWORD = env.str("DATACITE_PASSWORD", default=random_string())

# URL of the API, there is one for test and one for production
DATACITE_API_URL = env.str("DATACITE_API_URL", default="https://api.test.datacite.org")

# The desired state of the DOI: draft, registered or findable - only draft DOIs can be deleted
PUBLICATION_DOI_STATE = env.str("PUBLICATION_DOI_STATE", default="draft")
if PUBLICATION_DOI_STATE not in PUBLICATION_DOI_STATE_INFOS.keys():
    raise ImproperlyConfigured(
        f"Undefined state given for a publication DOI: {PUBLICATION_DOI_STATE}"
    )

# Some limitations, so that bots cannot enter too much
PUBLICATION_MAX_NUM_AUTHORS = 200
PUBLICATION_MAX_NUM_AFFILIATIONS_PER_AUTHOR = 20

#
# Analysis-specific settings
#
CONTACT_MECHANICS_KWARGS_LIMITS = {
    "nsteps": dict(min=1, max=50),
    "maxiter": dict(min=100, max=1000),
    "pressures": dict(maxlen=50),
}

# Configure watchman checks
WATCHMAN_CHECKS = watchman_constants.DEFAULT_CHECKS + (
    "topobank.taskapp.utils.celery_worker_check",
)

#
# Tabnav configuration
#
TABNAV_DISPLAY_HOME_TAB = True


# REQUEST PROFILER
# ------------------------------------------------------------------------------
# Default configuration is to ingore staff user, we override this here to log all requests
def REQUEST_PROFILER_GLOBAL_EXCLUDE_FUNC(x):
    return True


# Keep records for a month
REQUEST_PROFILER_LOG_TRUNCATION_DAYS = 30

# Upload method
UPLOAD_METHOD = env("TOPOBANK_UPLOAD_METHOD", default="POST")

# STORAGE
# ------------------------------------------------------------------------------
# Storage is configured in the specialization for testing, local and production
# deployment. The only setting here is to specify whether existing files will be
# deleted when manifests are created. This is sometimes needed in tests when files
# on the storage system are persistent, but should not be enabled in production to
# prevent data loss.
DELETE_EXISTING_FILES = env.bool("TOPOBANK_DELETE_EXISTING_FILES", default=False)

# TOPOBANK SPECIFIC
# ------------------------------------------------------------------------------
TOPOBANK_THUMBNAIL_FORMAT = "jpeg"  # File format for thumbnails
TOPOBANK_DELETE_DELAY = timedelta(days=7)  # Hold deleted datasets this long

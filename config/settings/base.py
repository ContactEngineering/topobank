"""
Base settings to build other settings files upon.
"""
from django.core.exceptions import ImproperlyConfigured
from pkg_resources import iter_entry_points
import environ

import topobank

ROOT_DIR = environ.Path(__file__) - 3  # (topobank/config/settings/base.py - 3 = topobank/)
APPS_DIR = ROOT_DIR.path('topobank')

env = environ.Env()

READ_DOT_ENV_FILE = env.bool('DJANGO_READ_DOT_ENV_FILE', default=False)
if READ_DOT_ENV_FILE:
    # OS environment variables take precedence over variables from .env
    env.read_env(str(ROOT_DIR.path('.env')))

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = env.bool('DJANGO_DEBUG', False)
# Local time zone. Choices are
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# though not all of them may be available with every OS.
# In Windows, this must be set to your system time zone.
TIME_ZONE = 'Europe/Berlin'
# https://docs.djangoproject.com/en/dev/ref/settings/#language-code
LANGUAGE_CODE = 'en-us'
# https://docs.djangoproject.com/en/dev/ref/settings/#site-id
SITE_ID = 1
# https://docs.djangoproject.com/en/dev/ref/settings/#use-i18n
USE_I18N = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-l10n
USE_L10N = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-tz
USE_TZ = True

# DATABASES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#databases

DATABASES = {
    'default': env.db('DATABASE_URL', default='postgres:///topobank'),
    # 'default': env.db('DATABASE_URL', default='sqlite:///topobank.db'),
}
DATABASES['default']['ATOMIC_REQUESTS'] = True

# URLS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#root-urlconf
ROOT_URLCONF = 'config.urls'
# https://docs.djangoproject.com/en/dev/ref/settings/#wsgi-application
WSGI_APPLICATION = 'config.wsgi.application'

# APPS
# ------------------------------------------------------------------------------
DJANGO_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',  # also use whitenoise with runserver
    'collectfast',  # must be inserted before 'staticfiles'
    'django.contrib.staticfiles',
    # 'django.contrib.humanize', # Handy template tags
    'django.contrib.admin',
    'django.contrib.postgres',  # needed for 'search' lookup
]
THIRD_PARTY_APPS = [
    'crispy_forms',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.orcid',
    'rest_framework',
    'fontawesomefree',
    'formtools',
    'bokeh',
    'termsandconditions',
    'storages',
    'guardian',
    'bootstrap_datepicker_plus',  # for datepicker, see https://github.com/monim67/django-bootstrap-datepicker-plus
    'django_select2',
    'django_tables2',
    'progressbarupload',
    'celery_progress',
    'notifications',
    'django_filters',
    'tagulous',
    'trackstats',
    'fullurl',
]
LOCAL_APPS = [
    # Your stuff: custom apps go here
    'topobank.users.apps.UsersAppConfig',
    'topobank.manager.apps.ManagerAppConfig',
    'topobank.analysis.apps.AnalysisAppConfig',
    'topobank.usage_stats.apps.UsageStatsAppConfig',
    'topobank.tabnav.apps.TabNavAppConfig',
    'topobank.publication.apps.PublicationAppConfig',
]

TOPOBANK_PLUGINS_IGNORE_CONFLICTS = env.bool('TOPOBANK_PLUGINS_IGNORE_CONFLICTS', default=False)
TOPOBANK_PLUGINS_EXCLUDE = env.list('TOPOBANK_PLUGINS_EXCLUDE', default=[])
PLUGIN_APPS = []
for entry_point in iter_entry_points(group='topobank.plugins', name=None):
    if entry_point.module_name in TOPOBANK_PLUGINS_EXCLUDE:
        continue
    PLUGIN_APPS.append(entry_point.module_name)

#
# PLUGIN_APPS = [
#     'topobank.statistical_analysis.apps.StatisticalAnalysisConfig',
#     'topobank.contact_analysis.apps.ContactAnalysisConfig',
# ]


# https://docs.djangoproject.com/en/dev/ref/settings/#installed-apps
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS + PLUGIN_APPS

# MIGRATIONS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#migration-modules
MIGRATION_MODULES = {
    'sites': 'topobank.contrib.sites.migrations'
}

# AUTO-CREATED PRIMARY KEYS
# ------------------------------------------------------------------------------
# New in Django 3.2.
# See: https://docs.djangoproject.com/en/3.2/releases/3.2/#customizing-type-of-auto-created-primary-keys
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# AUTHENTICATION
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#authentication-backends
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
    'guardian.backends.ObjectPermissionBackend',
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-user-model
AUTH_USER_MODEL = 'users.User'
# https://docs.djangoproject.com/en/dev/ref/settings/#login-redirect-url
LOGIN_REDIRECT_URL = 'home'
# https://docs.djangoproject.com/en/dev/ref/settings/#login-url
LOGIN_URL = 'account_login'

# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = [
    # https://docs.djangoproject.com/en/dev/topics/auth/passwords/#using-argon2-with-django
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
    'django.contrib.auth.hashers.BCryptPasswordHasher',
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# MIDDLEWARE
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#middleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # http://whitenoise.evans.io/en/latest/django.html#enable-whitenoise
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # Enable the following if you want to check T&C by middleware
    # this must be called before anonymous user replacement, otherwise anonymous users will
    # always be asked to accept terms and conditons
    'termsandconditions.middleware.TermsAndConditionsRedirectMiddleware',
    'topobank.middleware.anonymous_user_middleware',  # we need guardian's kind of anonymous user for API calls
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'topobank.usage_stats.middleware.count_request_middleware',
]

# STATIC
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT = str(ROOT_DIR('staticfiles'))
# https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = '/static/'
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS = [
    str(APPS_DIR.path('static')),
]
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#staticfiles-finders
STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
# STATICFILES_STORAGE = 'whitenoise.storage.ManifestStaticFilesStorage'
# test whether slow collect static comes from WhiteNoise

# for faster collection of static files
COLLECTFAST_STRATEGY = "collectfast.strategies.filesystem.FileSystemStrategy"
# we first keep using filesystem storage, may try S3 later


# MEDIA
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#media-root
MEDIA_ROOT = str(ROOT_DIR.path('media'))
# https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = '/media/'

# TEMPLATES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#templates
TEMPLATES = [
    {
        # https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-TEMPLATES-BACKEND
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # https://docs.djangoproject.com/en/dev/ref/settings/#template-dirs
        'DIRS': [
            str(APPS_DIR.path('templates')),
        ],
        'OPTIONS': {
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-debug
            'debug': DEBUG,
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-loaders
            # https://docs.djangoproject.com/en/dev/ref/templates/api/#loader-types
            'loaders': [
                'django.template.loaders.filesystem.Loader',
                'django.template.loaders.app_directories.Loader',
            ],
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'django.template.context_processors.tz',
                'django.contrib.messages.context_processors.messages',
                'topobank.context_processors.versions_processor',
                'topobank.context_processors.basket_processor',
                'topobank.tabnav.context_processors.fixed_tabs_processor',
            ],
        },
    },
]
# http://django-crispy-forms.readthedocs.io/en/latest/install.html#template-packs
CRISPY_TEMPLATE_PACK = 'bootstrap4'

# FIXTURES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#fixture-dirs
FIXTURE_DIRS = (
    str(APPS_DIR.path('fixtures')),
)

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = env('DJANGO_EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL.
ADMIN_URL = 'admin/'
# https://docs.djangoproject.com/en/dev/ref/settings/#admins
ADMINS = [
    ("""Michael Röttger""", 'roettger@tf.uni-freiburg.de'),
    ("""Lars Pastewka""", 'lars.pastewka@imtek.uni-freiburg.de')
]
# https://docs.djangoproject.com/en/dev/ref/settings/#managers
MANAGERS = ADMINS

# Celery
# ------------------------------------------------------------------------------
INSTALLED_APPS += ['topobank.taskapp.celeryapp.CeleryAppConfig']
if USE_TZ:
    # http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-timezone
    CELERY_TIMEZONE = TIME_ZONE
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-broker_url
CELERY_BROKER_URL = env('CELERY_BROKER_URL', default='redis://redis:6379/0')
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-result_backend
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND', default='redis://127.0.0.1:6379/0')
# we don't use rpc:// as default here, because Python 3.7 is not officially supported by celery 4.2
# and there is a problem with Python 3.7's keyword 'async' which is used in the celery code

CELERY_RESULT_PERSISTENT = True
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-accept_content
CELERY_ACCEPT_CONTENT = ['json']
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-task_serializer
CELERY_TASK_SERIALIZER = 'json'
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-result_serializer
CELERY_RESULT_SERIALIZER = 'json'
# TODO: set to whatever value is adequate in your circumstances
# CELERYD_TASK_TIME_LIMIT = 5 * 60
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#task-soft-time-limit
# TODO: set to whatever value is adequate in your circumstances
# CELERYD_TASK_SOFT_TIME_LIMIT = 60

# https://docs.celeryproject.org/en/stable/userguide/configuration.html#worker-cancel-long-running-tasks-on-connection-loss
CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS=True
# https://docs.celeryproject.org/en/stable/userguide/configuration.html?highlight=heartbeat#broker-heartbeat
CELERY_BROKER_HEARTBEAT=60
CELERY_REDIS_BACKEND_HEALTH_CHECK_INTERVAL=30

# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-broker_url
# CELERY_BROKER_URL = env('CELERY_BROKER_URL', default='django://')
# CELERY_BROKER_URL = 'amqp://guest:guest@localhost:5672//'
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-result_backend
# if CELERY_BROKER_URL == 'django://':
#     CELERY_RESULT_BACKEND = 'redis://'
# else:
#     CELERY_RESULT_BACKEND = CELERY_BROKER_URL

# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-accept_content
# CELERY_ACCEPT_CONTENT = ['json', 'pickle']
#  http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-task_serializer
# CELERY_TASK_SERIALIZER = 'pickle'
#  http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-result_serializer
# CELERY_RESULT_SERIALIZER = 'pickle' # because of arrays

# django-allauth
# ------------------------------------------------------------------------------
# https://django-allauth.readthedocs.io/en/latest/configuration.html
ACCOUNT_ALLOW_REGISTRATION = env.bool('DJANGO_ACCOUNT_ALLOW_REGISTRATION', True)

# https://django-allauth.readthedocs.io/en/latest/advanced.html?highlight=name#custom-user-models
ACCOUNT_EMAIL_REQUIRED = False
ACCOUNT_AUTHENTICATION_METHOD = 'username'
ACCOUNT_USERNAME_REQUIRED = False
# we keep the username field for now, because it is used in the "users" app
# ACCOUNT_USER_MODEL_USERNAME_FIELD = None

ACCOUNT_FORMS = {'signup': 'topobank.users.forms.SignupFormWithName'}

# https://django-allauth.readthedocs.io/en/latest/configuration.html
# ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
ACCOUNT_EMAIL_VERIFICATION = 'none'
# https://django-allauth.readthedocs.io/en/latest/configuration.html
ACCOUNT_ADAPTER = 'topobank.users.adapters.AccountAdapter'
# https://django-allauth.readthedocs.io/en/latest/configuration.html
SOCIALACCOUNT_ADAPTER = 'topobank.users.adapters.SocialAccountAdapter'
ACCOUNT_LOGOUT_ON_GET = True  # True: disable intermediate page

# Your stuff...
# ------------------------------------------------------------------------------



#
# Define permissions when using the rest framework
#
# Make sure that no one can retrieve data from other users, e.g. in view. See GH 168.
# This may help: https://www.django-rest-framework.org/api-guide/permissions/
# This seems to fit well: https://www.django-rest-framework.org/tutorial/4-authentication-and-permissions/
#
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    # 'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    #'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    #'PAGE_SIZE': 2,
}

# Version number used in the GUI
TOPOBANK_VERSION = topobank.__version__

#
# Settings for authentication with ORCID
#
SOCIALACCOUNT_PROVIDERS = {
    'orcid': {
        # Base domain of the API. Default value: 'orcid.org', for the production API
        # 'BASE_DOMAIN':'sandbox.orcid.org',  # for the sandbox API
        # Member API or Public API? Default: False (for the public API)
        # 'MEMBER_API': False,  # for the member API
    }
}
SOCIALACCOUNT_QUERY_EMAIL = True  # e-mail should be aquired from social account provider
def ACCOUNT_USER_DISPLAY(user):
    return user.name

#
# Settings for handling terms and conditions
#
TERMS_EXCLUDE_URL_LIST = {'/accounts/logout/'}
# TERMS_EXCLUDE_URL_PREFIX_LIST = {'/users/'}
TERMS_EXCLUDE_USERS_WITH_PERM = 'users.can_skip_terms'
TERMS_STORE_IP_ADDRESS = False

#
# Storage Settings
#
USE_S3_STORAGE = env.bool('USE_S3_STORAGE', default=False)

if USE_S3_STORAGE:
    # Enable this storage for the S3 backend
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    # DEFAULT_FILE_STORAGE = 'topobank.manager.storage_backends.MediaStorage'
    AWS_LOCATION = env.str('AWS_MEDIA_PREFIX', default='media')

    AWS_ACCESS_KEY_ID = env.str('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = env.str('AWS_SECRET_ACCESS_KEY')

    AWS_STORAGE_BUCKET_NAME = env.str('AWS_STORAGE_BUCKET_NAME', default='topobank-assets')

    AWS_AUTO_CREATE_BUCKET = True

    AWS_S3_ENDPOINT_URL = env.str('AWS_S3_ENDPOINT_URL', default='https://localhost:8082/')
    AWS_S3_USE_SSL = env.bool('AWS_S3_USE_SSL', default=True)
    AWS_S3_VERIFY = env.bool('AWS_S3_VERIFY', default=True)
    AWS_DEFAULT_ACL = None
    # Append extra characters if new files have the same name
    AWS_S3_FILE_OVERWRITE = False

#
# Settings for django-guardian
#
GUARDIAN_MONKEY_PATCH = False
GUARDIAN_RENDER_403 = True
# uses template "403.html" by default
# see https://django-guardian.readthedocs.io/en/stable/configuration.html#guardian-render-403

#
# Settings for django-tables2
#
DJANGO_TABLES2_TEMPLATE = 'django_tables2/bootstrap4.html'

#
# Setting for progress bar during upload
#
# see https://github.com/ouhouhsami/django-progressbarupload
#
FILE_UPLOAD_HANDLERS = (
    "progressbarupload.uploadhandler.ProgressBarUploadHandler",
    "django.core.files.uploadhandler.MemoryFileUploadHandler",
    "django.core.files.uploadhandler.TemporaryFileUploadHandler",
)
PROGRESSBARUPLOAD_INCLUDE_JQUERY = False

#
# Settings for tracking package versions for analyses
#
# list of tuples of form (import_name, expression_returning_version_string)
TRACKED_DEPENDENCIES = [
    ('SurfaceTopography', 'SurfaceTopography.__version__'),
    ('ContactMechanics', 'ContactMechanics.__version__'),
    ('NuMPI', 'NuMPI.__version__'),
    ('muFFT', 'muFFT.version.description()'),
    ('topobank', 'topobank.__version__'),
    ('numpy', 'numpy.__version__'),
    ('scipy', 'scipy.__version__'),
]

#
# Settings for notifications package
#
DJANGO_NOTIFICATIONS_CONFIG = {'USE_JSONFIELD': True}
# I would like to pass the target url to a notification

#
# Local references for "select2"
#
# An alternative is maybe "django-bower" which could be used
# to resolve all external javascript dependencies and install them
# locally in a defined way
SELECT2_JS = '/static/tagulous/lib/select2-4/js/select2.min.js'
SELECT2_CSS = '/static/tagulous/lib/select2-4/css/select2.min.css'
SELECT2_I18N_PATH = '/static/tagulous/lib/select2-4/js/i18n'
# The default for all these are pointers to Cloudflare CDN

#
# Settings for django-tagulous (tagging)
#
SERIALIZATION_MODULES = {
    'xml':    'tagulous.serializers.xml_serializer',
    'json':   'tagulous.serializers.json',
    'python': 'tagulous.serializers.python',
    'yaml':   'tagulous.serializers.pyyaml',
}

TAGULOUS_AUTOCOMPLETE_JS = (
    "tagulous/lib/select2-4/js/select2.full.min.js",
    "tagulous/tagulous.js",
    "tagulous/adaptor/select2-4.js",
)


#
# E-Mail address to contact us
#
CONTACT_EMAIL_ADDRESS = "support@contact.engineering"

#
# Publication settings
#
# set to None to disable check
MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS = env.int('MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS', 600)

CC_LICENSE_INFOS = {  # each element refers to two links: (description URL, full license text URL)
    'cc0-1.0': {
        'description_url': 'https://creativecommons.org/publicdomain/zero/1.0/',
        'legal_code_url': 'https://creativecommons.org/publicdomain/zero/1.0/legalcode',
        'title': 'CC0 1.0 Universal',
        'option_name': 'CC0 1.0 (Public Domain Dedication)',
        'spdx_identifier': 'CC0-1.0',
    },
    'ccby-4.0': {
        'description_url': 'https://creativecommons.org/licenses/by/4.0/',
        'legal_code_url': 'https://creativecommons.org/licenses/by/4.0/legalcode',
        'title': 'Creative Commons Attribution 4.0 International Public License',
        'option_name': 'CC BY 4.0',
        'spdx_identifier': 'CC-BY-4.0',
    },
    'ccbysa-4.0': {
        'description_url': 'https://creativecommons.org/licenses/by-sa/4.0/',
        'legal_code_url': 'https://creativecommons.org/licenses/by-sa/4.0/legalcode',
        'title': 'Creative Commons Attribution-ShareAlike 4.0 International Public License',
        'option_name': 'CC BY-SA 4.0',
        'spdx_identifier': 'CC-BY-SA-4.0',
    }
}
# For SPDX identifiers, see https://spdx.org/licenses/
# It may be useful to use these identifiers also everywhere in the code when identifying a license,
# but then we also need to change the existing entries in the database.

#
# Analysis-specific settings
#
CONTACT_MECHANICS_KWARGS_LIMITS = {
            'nsteps': dict(min=1, max=50),
            'maxiter': dict(min=100, max=1000),
            'pressures': dict(maxlen=50),
}

#
# Datacite settings (DOI creation)
#
PUBLICATION_DOI_STATE_INFOS = {
    'draft': {
        'description': 'only visible in Fabrica, DOI can be deleted',
    },
    'registered': {
        'description': 'registered with the DOI Resolver, cannot be deleted',
    },
    'findable': {
        'description': 'registered with the DOI Resolver and indexed in DataCite Search, cannot be deleted',
    }
}

# Prefix of the URL each DOI refers to, the short url of the publication is added
PUBLICATION_URL_PREFIX = env.str('PUBLICATION_URL_PREFIX', 'https://contact.engineering/go/')

# Set this to True if each publication must get a DOI on creation
PUBLICATION_DOI_MANDATORY = env.bool('PUBLICATION_DOI_MANDATORY', default=False)

# Prefix of the DOI to be generated, e.g. '10.82035'
PUBLICATION_DOI_PREFIX = env.str('PUBLICATION_DOI_PREFIX', '99.999')  # 99.999 is invalid, should start with '10.'

# These are the credentials for DataCite
DATACITE_USERNAME = env.str('DATACITE_USERNAME', 'testuser')
DATACITE_PASSWORD = env.str('DATACITE_PASSWORD', 'testpassword')

# URL of the API, there is one for test and one for production
DATACITE_API_URL = env.str('DATACITE_API_URL', default='https://api.test.datacite.org')

# The desired state of the DOI: draft, registered or findable - only draft DOIs can be deleted
PUBLICATION_DOI_STATE = env.str('PUBLICATION_DOI_STATE', default='draft')
if PUBLICATION_DOI_STATE not in PUBLICATION_DOI_STATE_INFOS.keys():
    raise ImproperlyConfigured(f"Undefined state given for a publication DOI: {PUBLICATION_DOI_STATE}")

# Some limitations, so that bots cannot enter too much
PUBLICATION_MAX_NUM_AUTHORS = 200
PUBLICATION_MAX_NUM_AFFILIATIONS_PER_AUTHOR = 20

#
# Settings related to contact characterization challenge
#
# Set to empty string in order to deactive corresponding test
CHALLENGE_REDIRECT_URL = env.str('CHALLENGE_REDIRECT_URL', default='https://forms.gle/GB3jLqJggbMmNfFm6')
# CHALLENGE_REDIRECT_URL = ''

#
# Performance related settings
#
DEFAULT_ALLOW_CACHE_FOR_LOW_LEVEL_TOPOGRAPHY = True


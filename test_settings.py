import os
import tempfile
from datetime import timedelta

SECRET_KEY = 'dummy'

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "django.contrib.postgres",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "rest_framework",
    "storages",
    "guardian",
    "notifications",
    "tagulous",
    "django_celery_results",
    "topobank.users.apps.UsersAppConfig",
    "topobank.authorization.apps.AuthorizationAppConfig",
    "topobank.files.apps.FilesAppConfig",
    "topobank.manager.apps.ManagerAppConfig",
    "topobank.analysis.apps.AnalysisAppConfig",
    "topobank.organizations.apps.OrganizationsAppConfig",
    "topobank.properties.apps.PropertiesAppConfig",
    "topobank.taskapp.celeryapp.CeleryAppConfig",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "topobank-test",
        "USER": "postgres",
        "PASSWORD": "",
        "HOST": "localhost",
        "PORT": "",
    }
}

AUTH_USER_MODEL = "users.User"
SITE_ID = 1
USE_TZ = True
TIME_ZONE = "CET"

# Celery test configuration
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_STORE_EAGER_RESULT = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "django-db"

# Other required basic settings
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

STATIC_URL = '/static/'
MEDIA_URL = '/media/'
MEDIA_ROOT = tempfile.mkdtemp()
os.makedirs(os.path.join(MEDIA_ROOT, 'analyses'), exist_ok=True)

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ),
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

CC_LICENSE_INFOS = {
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

TOPOBANK_MANAGER_QUEUE = "manager"
TOPOBANK_ANALYSIS_QUEUE = "analysis"
TOPOBANK_THUMBNAIL_FORMAT = "jpeg"
TOPOBANK_DELETE_DELAY = timedelta(days=7)
MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS = 600
PUBLICATION_ENABLED = True
PUBLICATION_DOI_STATE_INFOS = {
    "draft": {"description": "only visible in Fabrica, DOI can be deleted"},
    "registered": {"description": "registered with the DOI Resolver, cannot be deleted"},
    "findable": {"description": "registered with the DOI Resolver and indexed in DataCite Search, cannot be deleted"},
}
PUBLICATION_URL_PREFIX = "https://contact.engineering/go/"
PUBLICATION_DOI_MANDATORY = False
PUBLICATION_DOI_PREFIX = "99.999"
PUBLICATION_DOI_STATE = "draft"
PUBLICATION_MAX_NUM_AUTHORS = 200
PUBLICATION_MAX_NUM_AFFILIATIONS_PER_AUTHOR = 20

USE_S3_STORAGE = False
PLUGIN_MODULES = []

UPLOAD_METHOD = "POST"
BOKEH_OUTPUT_BACKEND = "canvas"
WEBAPP_URL = "http://localhost:5173/"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

ADMIN_URL = "admin/"
TRACKED_DEPENDENCIES = [
    (
        "topobank",
        "topobank.__version__",
        "MIT",
        "https://github.com/ContactEngineering/topobank",
    ),
    (
        "SurfaceTopography",
        "SurfaceTopography.__version__",
        "MIT",
        "https://github.com/ContactEngineering/SurfaceTopography",
    ),
    ("numpy", "numpy.__version__", "BSD 3-Clause", "https://numpy.org/"),
]

SERIALIZATION_MODULES = {
    "xml": "tagulous.serializers.xml_serializer",
    "json": "tagulous.serializers.json",
    "python": "tagulous.serializers.python",
    "yaml": "tagulous.serializers.pyyaml",
}

DJANGO_NOTIFICATIONS_CONFIG = {"USE_JSONFIELD": True}

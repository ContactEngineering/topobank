"""
Settings for the test suite.

This is the single definition; the top-level ``test_settings`` module that
``DJANGO_SETTINGS_MODULE`` names re-exports it, so that the copy an installed
``topobank`` exposes to downstream plugins and the copy the test run uses cannot
drift apart. See #1395.
"""

import os
import tempfile
from datetime import timedelta

import environ

env = environ.Env()

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
    "storages",
    "notifications",
    "tagulous",
    "django_celery_results",
    "topobank.testing.mock_auth.users.apps.UsersAppConfig",
    "topobank.testing.mock_auth.authorization.apps.AuthorizationAppConfig",
    "topobank.files.apps.FilesAppConfig",
    "topobank.manager.apps.ManagerAppConfig",
    "topobank.analysis.apps.AnalysisAppConfig",
    "topobank.testing.mock_auth.organizations.apps.OrganizationsAppConfig",
    "topobank.properties.apps.PropertiesAppConfig",
    "topobank.taskapp.celeryapp.CeleryAppConfig",
]

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://topobank:topobankpassword@localhost:5432/topobank-test"
    )
}

MIGRATION_MODULES = {
    "authorization": "topobank.testing.mock_auth.authorization.migrations",
    "organizations": "topobank.testing.mock_auth.organizations.migrations",
    "users": "topobank.testing.mock_auth.users.migrations",
}

AUTH_USER_MODEL = "users.User"
TOPOBANK_PERMISSION_MODEL = "authorization.PermissionSet"
TOPOBANK_ORGANIZATION_MODEL = "organizations.Organization"
TOPOBANK_ANONYMOUS_USER_GETTER = (
    "topobank.testing.mock_auth.users.anonymous.get_anonymous_user"
)
SITE_ID = 1
USE_TZ = True
TIME_ZONE = "Europe/Berlin"

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
    "default": {
        "BACKEND": env(
            "STORAGE_BACKEND", default="django.core.files.storage.FileSystemStorage"
        )
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Whether files live on an S3-compatible object store rather than on a local
# filesystem. This changes the upload flow: clients then upload directly to the
# object store and `Manifest.finish_upload` looks for the file at the expected
# storage location afterwards.
USE_S3_STORAGE = STORAGES["default"]["BACKEND"].endswith("S3Boto3Storage")

if USE_S3_STORAGE:
    # The defaults describe the SeaweedFS instance of the development stack.
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="admin")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="secret12")
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="topobank-test")
    AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default="http://localhost:9000")
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="us-east-1")
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    # Consecutive runs reuse the same bucket, so a file left behind by an
    # earlier run must not change the name a later run stores its file under.
    AWS_S3_FILE_OVERWRITE = True


CC_LICENSE_INFOS = {
    "cc0-1.0": {
        "description_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "legal_code_url": (
            "https://creativecommons.org/publicdomain/zero/1.0/legalcode"
        ),
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
        "legal_code_url": (
            "https://creativecommons.org/licenses/by-sa/4.0/legalcode"
        ),
        "title": (
            "Creative Commons Attribution-ShareAlike 4.0 International "
            "Public License"
        ),
        "option_name": "CC BY-SA 4.0",
        "spdx_identifier": "CC-BY-SA-4.0",
    },
}

TOPOBANK_MANAGER_QUEUE = "manager"
TOPOBANK_ANALYSIS_QUEUE = "analysis"
TOPOBANK_THUMBNAIL_FORMAT = "jpeg"
TOPOBANK_DELETE_DELAY = timedelta(days=7)
TOPOBANK_TEMPORARY_DELAY = timedelta(days=3)
TOPOBANK_ANALYSIS_DELETE_DELAY = timedelta(days=183)
TOPOBANK_REJECT_INCOMPLETE_METADATA = False
TOPOBANK_SPOOL_MAX_SIZE = 64 * 1024 * 1024
MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS = 600
PUBLICATION_ENABLED = True
PUBLICATION_DOI_STATE_INFOS = {
    "draft": {"description": "only visible in Fabrica, DOI can be deleted"},
    "registered": {
        "description": "registered with the DOI Resolver, cannot be deleted"
    },
    "findable": {
        "description": (
            "registered with the DOI Resolver and indexed in DataCite Search, "
            "cannot be deleted"
        )
    },
}
PUBLICATION_URL_PREFIX = "https://contact.engineering/go/"
PUBLICATION_DOI_MANDATORY = False
PUBLICATION_DOI_PREFIX = "99.999"
PUBLICATION_DOI_STATE = "draft"
PUBLICATION_MAX_NUM_AUTHORS = 200
PUBLICATION_MAX_NUM_AFFILIATIONS_PER_AUTHOR = 20

DELETE_EXISTING_FILES = True
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

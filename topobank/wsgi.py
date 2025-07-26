"""
WSGI config for the topobank project.
"""

import os
import sys

from django.core.wsgi import get_wsgi_application

# If we are running without DJANGO_DEBUG, then topobank has been installed via pip
if os.environ.get("DJANGO_DEBUG", default=False):
    # This allows easy placement of apps within the interior
    # topobank directory when running in debug mode.
    app_path = os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
    )
    sys.path.append(os.path.join(app_path, "topobank"))

# We defer to a DJANGO_SETTINGS_MODULE already in the environment. This breaks
# if running multiple sites in the same mod_wsgi process. To fix this, use
# mod_wsgi daemon mode with each site in its own daemon process, or use
# os.environ["DJANGO_SETTINGS_MODULE"] = "topobank.settings.production"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "topobank.settings.production")

# This application object is used by any WSGI server configured to use this
# file. This includes Django's development server, if the WSGI_APPLICATION
# setting points here.
application = get_wsgi_application()

# Apply WSGI middleware here.
# from helloworld.wsgi import HelloWorldApplication
# application = HelloWorldApplication(application)

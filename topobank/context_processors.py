from django.contrib.staticfiles.templatetags.staticfiles import static
from django.conf import settings
import django

import json
import bokeh
import celery

import PyCo

from topobank.manager.utils import current_selection_as_basket_items


def versions_processor(request):

    # key 'links': dicts with keys display_name:url

    versions = [
        dict(module='TopoBank',
             version=settings.TOPOBANK_VERSION,
             links={'Changelog': static('other/CHANGELOG.md')}), # needs 'manage.py collectstatic' before!
        dict(module='PyCo',
             version=PyCo.__version__,
             links={}),
        dict(module='Django',
             version=django.__version__,
             links={'Website': 'https://www.djangoproject.com/'}),
        dict(module='Celery',
             version=celery.__version__,
             links={'Website': 'http://www.celeryproject.org/'}),
        dict(module='Bokeh',
             version=bokeh.__version__,
             links={'Website': 'https://bokeh.pydata.org/en/latest/'}),

    ]

    return dict(versions=versions, contact_email_address=settings.CONTACT_EMAIL_ADDRESS)


def basket_processor(request):
    """Return JSON with select surfaces and topographies.

    Parameters
    ----------
    request

    Returns
    -------
    Dict with extra context, a key 'basket_items_json'
    which encodes all selected topographies and surfaces such they can be
    displayed on top of each page. See also base.html.
    """

    if not request.user.is_authenticated:
        return {}

    return dict(basket_items_json=json.dumps(current_selection_as_basket_items(request)))


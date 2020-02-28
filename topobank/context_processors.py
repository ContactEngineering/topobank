from django.contrib.staticfiles.templatetags.staticfiles import static
from django.conf import settings
from django.shortcuts import reverse
import django
import json
import bokeh
import celery

import PyCo

from topobank.manager.utils import selected_instances

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

    topographies, surfaces = selected_instances(request)

    basket_items = []
    for s in surfaces:
        unselect_url = reverse('manager:surface-unselect', kwargs=dict(pk=s.pk))
        basket_items.append(dict(name=s.name,
                                 type="surface",
                                 unselect_url=unselect_url,
                                 key=f"surface-{s.pk}"))
    for t in topographies:
        unselect_url = reverse('manager:topography-unselect', kwargs=dict(pk=t.pk))
        basket_items.append(dict(name=t.name,
                                 type="topography",
                                 unselect_url=unselect_url,
                                 key=f"topography-{t.pk}",
                                 surface_key=f"surface-{t.surface.pk}"))

    return dict(basket_items_json=json.dumps(basket_items))

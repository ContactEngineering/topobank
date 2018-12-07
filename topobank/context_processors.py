from django.contrib.staticfiles.templatetags.staticfiles import static

import PyCo


def versions_processor(request):

    versions = [
        dict(module='TopoBank',
             version='N/A',
             changelog_link=static('other/CHANGELOG.md')), # needs 'manage.py collectstatic' before!
        dict(module='PyCo',
             version=PyCo.__version__,
             changelog_link=''),
    ]

    return dict(versions=versions)

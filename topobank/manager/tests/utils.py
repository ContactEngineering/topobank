import pytest
from django.core.management import call_command
from django.conf import settings
from shutil import copyfile
import os.path
import logging

from topobank.users.models import User
from topobank.manager.models import Topography

_log = logging.getLogger(__name__)


@pytest.fixture
def two_topos(django_db_setup, django_db_blocker):

    #
    # Copy uploaded files at the correct places
    #
    # or use sth. like https://github.com/duncaningram/django-fixture-media
    #
    from_path = os.path.join(str(settings.ROOT_DIR),
                             'topobank/manager/fixtures/example4.txt')

    to_paths = ['topographies/user_1/example4.txt',
                'topographies/user_1/example4_VBYUbBc.txt',]

    for to_path in to_paths:
        to_path = os.path.join(settings.MEDIA_ROOT, to_path)
        _log.info("Copying fixture file '{}' -> '{}'..".format(from_path, to_path))
        copyfile(from_path, to_path)

    #
    # Load database from YAML file
    #
    with django_db_blocker.unblock():
        call_command('loaddata', 'two_topographies.yaml')

        # Fix the passwords of fixtures
        for user in User.objects.all():
            user.set_password(user.password)
            user.save()

        # like this we can have clear-text passwords in test fixtures


def export_reponse_as_html(response, fname='/tmp/response.html'):
    """
    Helper function which can be used for debugging.

    :param response: HTTPResponse
    :param fname: name of HTML output file
    """
    f = open(fname, mode='w')

    f.write(response.content.decode('utf-8').replace('\\n','\n'))
    f.close()

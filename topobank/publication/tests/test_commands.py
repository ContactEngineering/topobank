"""
Test management commands for publication app.
"""
from django.core.management import call_command
from django.conf import settings

import pytest
import topobank.publication.models

from .utils import PublicationFactory


@pytest.mark.django_db
def test_complete_dois(mocker, settings):
    pub1 = PublicationFactory(doi_name='10.4545/abcde')
    pub2 = PublicationFactory()
    pub3 = PublicationFactory()

    settings.PUBLICATION_DOI_MANDATORY = True
    m = mocker.patch('topobank.publication.models.Publication.create_doi')

    call_command('complete_dois', do_it=True, force_draft=True)

    m.assert_called()
    assert m.call_count == 2







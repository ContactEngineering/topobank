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


@pytest.mark.django_db
def test_renew_containers(mocker, settings):
    pub1 = PublicationFactory(doi_name='10.4545/abcde')  # should not get a new container
    pub2 = PublicationFactory(doi_name='10.4545/xyz')  # should not get a new container
    pub3 = PublicationFactory()  # only this one should get a new container

    settings.PUBLICATION_DOI_MANDATORY = True
    m = mocker.patch('topobank.publication.models.Publication.renew_container')

    call_command('renew_containers')

    m.assert_called()
    assert m.call_count == 1









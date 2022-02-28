"""
Helpers for testing the publication app.
"""
import factory
import datetime
import short_url
import json

from topobank.publication.models import Publication
from topobank.manager.tests.utils import SurfaceFactory
from topobank.users.tests.test_utils import UserFactory


class PublicationFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = Publication

    surface = factory.SubFactory(SurfaceFactory)
    original_surface = factory.SubFactory(SurfaceFactory)

    short_url = factory.LazyAttribute(lambda self: short_url.encode_url(self.surface.id))
    publisher = factory.SubFactory(UserFactory)
    # publisher_orcid_id = factory.LazyAttribute(lambda self: self.publisher.orcid_id)
    version = "1"
    datetime = datetime.datetime.now()
    license = 'cc0-1.0'
    authors_json = factory.List(
        [
            {'first_name': 'Harry',
             'last_name': 'Potter',
             'orcid_id': '9999-9999-9999-9999',
             'affiliations': [
                 {
                     'name': 'University of Freiburg',
                     'ror_id': '0245cg223'
                 },
                 {
                     'name': 'Hogwarts'
                 }
             ]
             },
            {
                'first_name': 'Hermoine',
                'last_name': 'Granger',
                'orcid_id': '9999-9999-9999-999X',
                'affiliations': [
                    {
                        'name': 'Hogwarts'
                    }
                ]
            }
        ]
    )
    # container = models.FileField(max_length=50, default='')
    doi_name = ''
    doi_state = Publication.DOI_STATE_DRAFT

import logging
import math
from io import BytesIO

from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.http import quote
from django.http.request import urljoin
from django.conf import settings

from datacite import schema42, DataCiteRESTClient
from datacite.errors import DataCiteError, HttpError

from .utils import (AlreadyPublishedException, DOICreationException, NewPublicationTooFastException,
                    PublicationsDisabledException, PublicationException, UnknownCitationFormat,
                    set_publication_permissions)

_log = logging.getLogger(__name__)

MAX_LEN_AUTHORS_FIELD = 512

CITATION_FORMAT_FLAVORS = ['html', 'ris', 'bibtex', 'biblatex']
DEFAULT_KEYWORDS = ['surface', 'topography']





class Publication(models.Model):
    """Represents a publication of a digital surface twin."""
    LICENSE_CHOICES = [(k, settings.CC_LICENSE_INFOS[k]['option_name'])
                       for k in ['cc0-1.0', 'ccby-4.0', 'ccbysa-4.0']]
    DOI_STATE_DRAFT = 'draft'
    DOI_STATE_REGISTERED = 'registered'
    DOI_STATE_FINDABLE = 'findable'
    DOI_STATE_CHOICES = [(k, settings.PUBLICATION_DOI_STATE_INFOS[k]['description'])
                         for k in [DOI_STATE_DRAFT, DOI_STATE_REGISTERED, DOI_STATE_FINDABLE]]

    short_url = models.CharField(max_length=10, unique=True, null=True)
    surface = models.OneToOneField("manager.Surface", on_delete=models.PROTECT, related_name='publication')
    original_surface = models.ForeignKey("manager.Surface", on_delete=models.PROTECT,
                                         # original surface can no longer be deleted once published
                                         null=True, related_name='derived_publications')
    publisher = models.ForeignKey("users.User", on_delete=models.PROTECT)
    publisher_orcid_id = models.CharField(max_length=19, default='')  # 16 digits including 3 dashes
    version = models.PositiveIntegerField(default=1)
    datetime = models.DateTimeField(auto_now_add=True)
    license = models.CharField(max_length=12, choices=LICENSE_CHOICES, blank=False, default='')
    authors_json = models.JSONField(default=list)
    datacite_json = models.JSONField(default=dict)
    container = models.FileField(max_length=50, default='')
    doi_name = models.CharField(max_length=50, default='')  # part of DOI which starts with 10.
    # if empty, the DOI has not been generated yet
    doi_state = models.CharField(max_length=10, choices=DOI_STATE_CHOICES, default='')

    def get_authors_string(self):
        """Return author names as comma-separated string in correct order.
        """
        return ", ".join([f"{a['first_name']} {a['last_name']}" for a in self.authors_json])

    def get_absolute_url(self):
        return reverse('publication:go', args=[self.short_url])

    def get_full_url(self):
        """Return URL which should be used to permanently point to this publication.

        If the publication has a DOI, this will be it's URL, otherwise
        it's a URL pointing to this web app.
        """
        if self.has_doi:
            return self.doi_url
        else:
            return urljoin(settings.PUBLICATION_URL_PREFIX, self.short_url)

    def get_citation(self, flavor):
        if flavor not in CITATION_FORMAT_FLAVORS:
            raise UnknownCitationFormat(flavor)
        method_name = '_get_citation_as_' + flavor
        return getattr(self, method_name)()

    def _get_citation_as_html(self):
        s = '{authors}. ({year}). contact.engineering. <em>{surface.name} (Version {version})</em>.'
        s += ' <a href="{publication_url}">{publication_url}</a>'
        s = s.format(
            authors=self.get_authors_string(),
            year=self.datetime.year,
            version=self.version,
            surface=self.surface,
            publication_url=self.get_full_url(),
        )
        return s

    def _get_citation_as_ris(self):
        # see http://refdb.sourceforge.net/manual-0.9.6/sect1-ris-format.html
        # or  https://en.wikipedia.org/wiki/RIS_(file_format)
        # or  https://web.archive.org/web/20120526103719/http://refman.com/support/risformat_intro.asp
        #     https://web.archive.org/web/20120717122530/http://refman.com/support/direct%20export.zip
        s = ""

        def add(key, value):
            nonlocal s
            s += f"{key}  - {value}\n"

        # Electronic citation / Website
        add('TY', 'ELEC')
        # Title
        add('TI', f"{self.surface.name} (Version {self.version})")
        # Authors
        for author in self.get_authors_string().split(','):
            add('AU', author.strip())
        # Publication Year
        add('PY', format(self.datetime, '%Y/%m/%d/'))
        # URL
        add('UR', self.get_full_url())
        # Name of Database
        add('DB', 'contact.engineering')

        # Notes
        add('N1', self.surface.description)

        # add keywords, defaults ones and tags
        for kw in DEFAULT_KEYWORDS:
            add('KW', kw)
        for t in self.surface.tags.all():
            add('KW', t.name)

        # End of record, must be empty and last tag
        add('ER', '')

        return s.strip()

    def _get_citation_as_bibtex(self):

        title = f"{self.surface.name} (Version {self.version})"
        shortname = f"{self.surface.name}_v{self.version}".lower().replace(' ', '_')
        keywords = ",".join(DEFAULT_KEYWORDS)
        if self.surface.tags.count() > 0:
            keywords += "," + ",".join(t.name for t in self.surface.tags.all())

        s = """
        @misc{{
            {shortname},
            title  = {{{title}}},
            author = {{{author}}},
            year   = {{{year}}},
            note   = {{{note}}},
            keywords = {{{keywords}}},
            howpublished = {{{publication_url}}},
        }}
        """.format(title=title,
                   author=self.get_authors_string().replace(', ', ' and '),
                   year=self.datetime.year,
                   note=self.surface.description,
                   publication_url=self.get_full_url(),
                   keywords=keywords,
                   shortname=shortname,
                   )

        return s.strip()

    def _get_citation_as_biblatex(self):

        shortname = f"{self.surface.name}_v{self.version}".lower().replace(' ', '_')
        keywords = ",".join(DEFAULT_KEYWORDS)
        if self.surface.tags.count() > 0:
            keywords += "," + ",".join(t.name for t in self.surface.tags.all())

        s = """
        @online{{
            {shortname},
            title  = {{{title}}},
            version = {{{version}}},
            author = {{{author}}},
            year   = {{{year}}},
            month  = {{{month}}},
            date   = {{{date}}},
            note   = {{{note}}},
            keywords = {{{keywords}}},
            url = {{{url}}},
            urldate = {{{urldate}}}
        }}
        """.format(title=self.surface.name,
                   version=self.version,
                   author=self.get_authors_string().replace(', ', ' and '),
                   year=self.datetime.year,
                   month=self.datetime.month,
                   date=format(self.datetime, "%Y-%m-%d"),
                   note=self.surface.description,
                   url=self.get_full_url(),
                   urldate=format(timezone.now(), "%Y-%m-%d"),
                   keywords=keywords,
                   shortname=shortname,
                   )

        return s.strip()

    @property
    def storage_prefix(self):
        """Return prefix used for storage.
        https://docs.djangoproject.com/en/2.2/ref/models/fields/#django.db.models.FileField.upload_to
        Looks like a relative path to a directory.
        If storage is on filesystem, the prefix should correspond
        to a real directory.
        """
        return "publications/{}".format(self.short_url)

    @property
    def container_storage_path(self):
        """Return relative path of container in storage."""
        return f"{self.storage_prefix}/ce-{self.short_url}.zip"

    @property
    def doi_url(self):
        """Return DOI as URL string or return None if DOI hasn't been generated yet."""
        # This depends on in which state the DOI -
        # this is useful in development of DOIs are in "draft" mode
        if self.doi_name == '':
            return None
        elif self.doi_state == Publication.DOI_STATE_DRAFT:
            return urljoin("https://doi.test.datacite.org/dois/", quote(self.doi_name, safe=''))
        else:
            return (f"https://doi.org/{self.doi_name}")  # here we keep the slash

    @property
    def has_doi(self):
        """Returns True, if this publication already has a doi."""
        return self.doi_name != ''

    @property
    def has_container(self):
        """Returns True, if this publication already has an non-empty container file."""
        return self.container != '' and self.container.size > 0

    def create_doi(self, force_draft=False):
        """Create DOI at datacite using available information.

        Parameters
        ----------
        force_draft: bool
            If True, the DOI state will be 'draft' and can be deleted later.
            If False, the system settings will be used, which could be either
            'draft', 'registered', or 'findable'. The later two cannot be
            deleted.

        Raises
        ------
        DOICreationException
            Is raised if DOI creation fails for some reason. The error message gives more details.
        """

        # "DOI name" is created from prefix and suffix, like this: <doi_prefix>/<doi_suffix>
        doi_suffix = "ce-" + self.short_url
        doi_name = settings.PUBLICATION_DOI_PREFIX + "/" + doi_suffix

        license_infos = settings.CC_LICENSE_INFOS[self.license]

        creators = []
        for author in self.authors_json:
            creator = {
                'name': f"{author['last_name']}, {author['first_name']}",
                'nameType': 'Personal',
                'givenName': author['first_name'],
                'familyName': author['last_name'],
            }

            #
            # Add affiliations, leave out ROR if not given
            #
            creator_affiliations = []
            for aff in author['affiliations']:
                creator_aff = {
                    'name': aff['name']
                }
                if aff['ror_id']:
                    creator_aff.update(
                        {
                            'schemeUri': "https://ror.org/",
                            'affiliationIdentifier': f"https://ror.org/{aff['ror_id']}",
                            'affiliationIdentifierScheme': "ROR",
                        })
                creator_affiliations.append(creator_aff)
            creator['affiliation'] = creator_affiliations

            if author['orcid_id']:
                creator.update({
                    'nameIdentifiers': [
                        {
                            'schemeUri': "https://orcid.org",
                            'nameIdentifierScheme': 'ORCID',
                            'nameIdentifier': f"https://orcid.org/{author['orcid_id']}"
                        }
                    ]
                })
            creators.append(creator)

        #
        # Now construct the full dataset using the creators
        #
        data = {
            #
            # Mandatory
            # ---------
            #
            # Identifier
            'identifiers': [
                {  # plural! See Issue 70
                    'identifierType': 'DOI',
                    'identifier': doi_name,
                }
            ],
            # Creator
            'creators': creators,
            # Title
            'titles': [
                {'title': self.surface.name, }
            ],
            # Publisher
            'publisher': 'contact.engineering',
            # PublicationYear
            'publicationYear': str(self.datetime.year),
            # ResourceType
            'types': {
                'resourceType': 'Dataset',
                'resourceTypeGeneral': 'Dataset'
            },
            #
            # Recommended or Optional
            # -----------------------
            #
            # # Subject
            'subjects': [
                {
                    "subject": "FOS: Materials engineering",
                    "valueUri": "http://www.oecd.org/science/inno/38235147.pdf",
                    "schemeUri": "http://www.oecd.org/science/inno",
                    "subjectScheme": "Fields of Science and Technology (FOS)"
                },  # included in result JSON
            ],
            # # Contributor
            # # Date
            'dates': [
                {
                    'dateType': 'Submitted',
                    'date': self.datetime.isoformat()
                }  # included in result JSON
            ],
            # # Language
            # # AlternateIdentifier
            # # RelatedIdentifier
            # # Size
            # # Format
            # # Version
            'version': str(self.version),
            # # Rights
            'rightsList': [
                {
                    'rightsURI': license_infos['legal_code_url'],
                    'rightsIdentifier': license_infos['spdx_identifier'],
                    'rightsIdentifierSchema': 'SPDX',
                    'schemeURI': 'https://spdx.org/licenses'
                },
            ],
            # # Description
            'descriptions': [
                {
                    # 'lang': 'en',  # key lang doesn't exist in version 4.2
                    'descriptionType': 'Abstract',
                    'description': self.surface.description,
                },  # missing in result
            ],
            # # GeoLocation
            # # FundingReference
            # #
            # # Other (not based on schema 4.2)
            # # -------------------------------
            # # Is the following needed? Since it referes to the schema, this key is not part of the schema
            'schemaVersion': 'http://datacite.org/schema/kernel-4',
            # 'url': "https://contact.engineering/go/btpax",
            # 'doi': "10.82035/ce-btpax"
        }

        if not schema42.validate(data):
            raise DOICreationException("Given data does not validate according to DataCite Schema 4.22!")

        client_kwargs = dict(
            username=settings.DATACITE_USERNAME,
            password=settings.DATACITE_PASSWORD,
            prefix=settings.PUBLICATION_DOI_PREFIX,
            url=settings.DATACITE_API_URL
        )
        requested_doi_state = Publication.DOI_STATE_DRAFT if force_draft else settings.PUBLICATION_DOI_STATE
        try:
            _log.info(f'Connecting to DataCite REST API at {settings.DATACITE_API_URL} for DOI '
                      f'prefix {settings.PUBLICATION_DOI_PREFIX}...')
            rest_client = DataCiteRESTClient(**client_kwargs)
            pub_full_url = self.get_full_url()

            if requested_doi_state == Publication.DOI_STATE_DRAFT:
                _log.info(f"Creating draft DOI '{doi_name}' for publication '{self.short_url}' without URL link...")
                rest_client.draft_doi(data, doi=doi_name)
                _log.info(f"Linking draft DOI '{doi_name}' for publication '{self.short_url}' to URL {pub_full_url}...")
                rest_client.update_url(doi=doi_name, url=pub_full_url)
            elif requested_doi_state == Publication.DOI_STATE_REGISTERED:
                _log.info(
                    f"Creating registered DOI '{doi_name}' for publication '{self.short_url}' linked to {pub_full_url}...")
                rest_client.private_doi(data, url=pub_full_url, doi=doi_name)
            elif requested_doi_state == Publication.DOI_STATE_FINDABLE:
                _log.info(
                    f"Creating findable DOI '{doi_name}' for publication '{self.short_url}' linked to {pub_full_url}...")
                rest_client.public_doi(data, url=pub_full_url, doi=doi_name)
            else:
                raise DataCiteError(f"Requested DOI state {requested_doi_state} is unknown.")
            _log.info("Done.")
        except (DataCiteError, HttpError) as exc:
            msg = f"DOI creation failed, reason: {exc}"
            _log.error(msg)
            raise DOICreationException(msg) from exc

        #
        # Finally, set DOI name and state
        #
        _log.info("Saving additional data to publication record..")
        self.doi_name = doi_name
        self.doi_state = requested_doi_state
        self.datacite_json = data
        self.save()
        _log.info(f"Done creating DOI for publication '{self.short_url}'.")

    def renew_container(self):
        """Renew container file or create it if not existent.
        """
        from topobank.manager.containers import write_surface_container
        container_bytes = BytesIO()
        _log.info(f"Preparing container for publication '{self.short_url}'..")
        write_surface_container(container_bytes, [self.surface])
        _log.info(f"Saving container for publication with URL {self.short_url} to storage for later..")
        container_bytes.seek(0)  # rewind
        self.container.save(self.container_storage_path, container_bytes)
        _log.info("Done.")

    @staticmethod
    def publish(surface, license, authors):
        """Publish surface.

        An immutable copy is created along with a publication entry.
        The latter is returned.

        Parameters
        ----------
        license: str
            One of the keys of LICENSE_CHOICES
        authors: list
            List of authors as list of dicts, where each dict has the
            form as in the example below. Will be saved as-is in JSON
            format and will be used for creating a DOI.

        Returns
        -------
        Publication

        (Fictional) Example of a dict representing an author:

        {
            'first_name': 'Melissa Kathrin'
            'last_name': 'Miller',
            'orcid_id': '1234-1234-1234-1224',
            'affiliations': [
                {
                    'name': 'University of Westminster',
                    'ror_id': '04ycpbx82'
                },
                {
                    'name': 'New York University Paris',
                    'ror_id': '05mq03431'
                },
            ]
        }

        """
        if not settings.PUBLICATION_ENABLED:
            raise PublicationsDisabledException()

        if surface.is_published:
            raise AlreadyPublishedException()

        latest_publication = Publication.objects.filter(original_surface=surface).order_by('version').last()
        #
        # We limit the publication rate
        #
        min_seconds = settings.MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS
        if (latest_publication is not None) and (min_seconds is not None):
            delta_since_last_pub = timezone.now() - latest_publication.datetime
            delta_secs = delta_since_last_pub.total_seconds()
            if delta_secs < min_seconds:
                raise NewPublicationTooFastException(latest_publication, math.ceil(min_seconds - delta_secs))

        #
        # Create a copy of this surface
        #
        copy = surface.deepcopy()

        try:
            set_publication_permissions(copy)
        except PublicationException as exc:
            # see GH 704
            _log.error(f"Could not set permission for copied surface to publish ... "
                       f"deleting copy (surface {copy.pk}) of surface {surface.pk}.")
            copy.delete()
            raise

        #
        # Create publication
        #
        if latest_publication:
            version = latest_publication.version + 1
        else:
            version = 1

        #
        # Save local reference for the publication
        #
        pub = Publication.objects.create(surface=copy, original_surface=surface,
                                         authors_json=authors,
                                         license=license,
                                         version=version,
                                         publisher=surface.creator,
                                         publisher_orcid_id=surface.creator.orcid_id)

        #
        # Try to create DOI - if this doesn't work, rollback
        #
        if settings.PUBLICATION_DOI_MANDATORY:
            try:
                pub.create_doi()
            except DOICreationException as exc:
                _log.error("DOI creation failed, reason: %s", exc)
                _log.warning(f"Cannot create publication with DOI, deleting copy (surface {copy.pk}) of "
                             f"surface {surface.pk} and publication instance.")
                pub.delete()  # need to delete pub first because it references copy
                copy.delete()
                raise PublicationException(f"Cannot create DOI, reason: {exc}") from exc
        else:
            _log.info("Skipping creation of DOI, because it is not configured as mandatory.")

        _log.info(f"Published surface {surface.name} (id: {surface.id}) " + \
                  f"with license {license}, version {version}, authors '{authors}'")
        _log.info(f"Direct URL of publication: {pub.get_absolute_url()}")
        _log.info(f"DOI name of publication: {pub.doi_name}")

        return pub

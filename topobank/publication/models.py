from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.http import quote
from django.http.request import urljoin
from django.conf import settings

from datacite import schema42, DataCiteRESTClient
from datacite.errors import DataCiteError

from topobank.users.models import User

MAX_LEN_AUTHORS_FIELD = 512

CITATION_FORMAT_FLAVORS = ['html', 'ris', 'bibtex', 'biblatex']
DEFAULT_KEYWORDS = ['surface', 'topography']


class UnknownCitationFormat(Exception):
    """Exception thrown when an unknown citation format should be handled."""

    def __init__(self, flavor):
        self._flavor = flavor

    def __str__(self):
        return f"Unknown citation format flavor '{self._flavor}'."


class DOICreationException(Exception):
    pass


class Publication(models.Model):
    """Represents a publication of a digital surface twin."""
    LICENSE_CHOICES = [(k, settings.CC_LICENSE_INFOS[k]['option_name'])
                       for k in ['cc0-1.0', 'ccby-4.0', 'ccbysa-4.0']]
    DOI_STATE_DRAFT = 'draft'
    DOI_STATE_REGISTERED = 'registered'
    DOI_STATE_FINDABLE = 'findable'
    DOI_STATE_CHOICES = [ (k, settings.PUBLICATION_DOI_STATE_INFOS[k]['description'])
                           for k in [DOI_STATE_DRAFT, DOI_STATE_REGISTERED, DOI_STATE_FINDABLE]]

    short_url = models.CharField(max_length=10, unique=True, null=True)
    surface = models.OneToOneField("manager.Surface", on_delete=models.PROTECT, related_name='publication')
    original_surface = models.ForeignKey("manager.Surface", on_delete=models.SET_NULL,
                                         null=True, related_name='derived_publications')
    publisher = models.ForeignKey("users.User", on_delete=models.PROTECT)
    publisher_orcid_id = models.CharField(max_length=19, default='')  # 16 digits including 3 dashes
    version = models.PositiveIntegerField(default=1)
    datetime = models.DateTimeField(auto_now_add=True)
    license = models.CharField(max_length=12, choices=LICENSE_CHOICES, blank=False, default='')
    authors_json = models.JSONField(default=list)
    container = models.FileField(max_length=50, default='')
    doi_name = models.CharField(max_length=50, null=True)  # part of DOI which starts with 10.
    # if null, the DOI has not been generated yet
    doi_state = models.CharField(max_length=10, choices=DOI_STATE_CHOICES, null=True)

    def get_authors_string(self):
        """Return author names as comma-separated string in correct order.
        """
        return ", ".join([f"{a['first_name']} {a['last_name']}" for a in self.authors_json])

    def get_absolute_url(self):
        return reverse('publication:go', args=[self.short_url])

    def get_full_url(self):
        return urljoin(settings.PUBLICATION_URL_PREFIX, self.short_url)

    def get_citation(self, flavor, request):
        if flavor not in CITATION_FORMAT_FLAVORS:
            raise UnknownCitationFormat(flavor)
        method_name = '_get_citation_as_' + flavor
        return getattr(self, method_name)(request)

    def _get_citation_as_html(self, request):
        s = '{authors}. ({year}). contact.engineering. <em>{surface.name} (Version {version})</em>.'
        s += ' <a href="{publication_url}">{publication_url}</a>'
        s = s.format(
            authors=self.get_authors_string(),
            year=self.datetime.year,
            version=self.version,
            surface=self.surface,
            publication_url=self.doi_url,
        )
        return mark_safe(s)

    def _get_citation_as_ris(self, request):
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
        add('UR', self.doi_url)
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

    def _get_citation_as_bibtex(self, request):

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
                   publication_url=self.doi_url,
                   keywords=keywords,
                   shortname=shortname,
                   )

        return s.strip()

    def _get_citation_as_biblatex(self, request):

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
                   url=self.doi_url,
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
        return "publications/{}/".format(self.short_url)

    @property
    def container_storage_path(self):
        """Return relative path of container in storage."""
        return f"{self.storage_prefix}container.zip"

    @property
    def doi_url(self):
        """Return DOI as URL string or return None if DOI hasn't been generated yet."""
        # This depends on in which state the DOI -
        # this is useful in development of DOIs are in "draft" mode
        if self.doi_name is None:
            return None
        elif self.doi_state == Publication.DOI_STATE_DRAFT:
            return urljoin("https://doi.test.datacite.org/dois/", quote(self.doi_name, safe=''))
        else:
            return(f"https://doi.org/{self.doi_name}")  # here we keep the slash

    def create_doi(self):
        """Create DOI at datacite using available information.

        Raises

            DOICreationException
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
                            'nameIdentifier': f"https://orcid.org/{author['orcid_id']}"  # TODO leave out if no orcid_id
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

        requested_doi_state = settings.PUBLICATION_DOI_STATE
        try:
            rest_client = DataCiteRESTClient(**client_kwargs)
            pub_full_url = self.get_full_url()

            if requested_doi_state == Publication.DOI_STATE_DRAFT:
                rest_client.draft_doi(data, doi=doi_name)
                rest_client.update_url(doi=doi_name, url=pub_full_url)
            elif requested_doi_state == Publication.DOI_STATE_REGISTERED:
                rest_client.private_doi(data, url=pub_full_url, doi=doi_name)
            elif requested_doi_state == Publication.DOI_STATE_FINDABLE:
                rest_client.public_doi(data, url=pub_full_url, doi=doi_name)
            else:
                raise DataCiteError(f"Requested DOI state {requested_doi_state} is unknown.")
        except DataCiteError as exc:
            raise DOICreationException(f"DOI creation failed, reason: {exc}") from exc

        #
        # Finally, set DOI name and state
        #
        self.doi_name = doi_name
        self.doi_state = settings.PUBLICATION_DOI_STATE
        self.save()

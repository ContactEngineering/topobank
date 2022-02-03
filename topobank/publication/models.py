from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.conf import settings
from django.core.validators import RegexValidator

from sortedm2m.fields import SortedManyToManyField

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


class Affiliation(models.Model):
    """An institution a researcher belongs to."""
    name = models.CharField(max_length=100)
    ror_id = models.CharField(max_length=9,
                              null=True,
                              validators=[
                                RegexValidator(r'^0[^ilouILOU]{6}[0-9]{2}')
                              ])  # see https://ror.org/facts/


class Researcher(models.Model):
    first_name = models.CharField(max_length=60)
    last_name = models.CharField(max_length=60)
    orcid_id = models.CharField(max_length=19,
                                null=True,
                                validators=[
                                    RegexValidator(r'^[0-9]{4}-[0-9]{4}-[0-9]{4}')
                                ])  # 16 digit-number with 3 hyphens inbetween
    affiliations = SortedManyToManyField(Affiliation)
    user = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)

    def orcid_identifier(self):
        """This is the ORCID ID as URL.

        Returns
        -------
        URL of the form https://orcid.org/xxxx-xxxx-xxxx-xxxx
        """
        return f"https://orcid.org/{self.orcid_id}"


class Publication(models.Model):

    LICENSE_CHOICES = [(k, settings.CC_LICENSE_INFOS[k]['option_name'])
                       for k in ['cc0-1.0', 'ccby-4.0', 'ccbysa-4.0']]

    short_url = models.CharField(max_length=10, unique=True, null=True)
    surface = models.OneToOneField("manager.Surface", on_delete=models.PROTECT, related_name='publication')
    original_surface = models.ForeignKey("manager.Surface", on_delete=models.SET_NULL,
                                         null=True, related_name='derived_publications')
    publisher = models.ForeignKey("users.User", on_delete=models.PROTECT)
    publisher_orcid_id = models.CharField(max_length=19, default='')  # 16 digits including 3 dashes
    version = models.PositiveIntegerField(default=1)
    datetime = models.DateTimeField(auto_now_add=True)
    license = models.CharField(max_length=12, choices=LICENSE_CHOICES, blank=False, default='')
    # authors = models.CharField(max_length=MAX_LEN_AUTHORS_FIELD)
    authors = SortedManyToManyField(Researcher)
    container = models.FileField(max_length=50, default='')

    def get_authors_string(self):
        """Return author names as comma-separated string in correct order.
        """
        return ", ".join([f"{a.first_name} {a.last_name}" for a in self.authors.all()])

    def get_absolute_url(self):
        return reverse('publication:go', args=[self.short_url])

    def get_full_url(self, request):
        return request.build_absolute_uri(self.get_absolute_url())

    def get_citation(self, flavor, request):
        if flavor not in CITATION_FORMAT_FLAVORS:
            raise UnknownCitationFormat(flavor)
        method_name = '_get_citation_as_'+flavor
        return getattr(self, method_name)(request)

    def _get_citation_as_html(self, request):
        s = '{authors}. ({year}). contact.engineering. <em>{surface.name} (Version {version})</em>.'
        s += ' <a href="{publication_url}">{publication_url}</a>'
        s = s.format(
            authors=self.authors,
            year=self.datetime.year,
            version=self.version,
            surface=self.surface,
            publication_url=self.get_full_url(request),
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
        for author in self.authors.split(','):
            add('AU', author.strip())
        # Publication Year
        add('PY', format(self.datetime, '%Y/%m/%d/'))
        # URL
        add('UR', self.get_full_url(request))
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
        shortname = f"{self.surface.name}_v{self.version}".lower().replace(' ','_')
        keywords = ",".join(DEFAULT_KEYWORDS)
        if self.surface.tags.count()>0:
            keywords += ","+",".join(t.name for t in self.surface.tags.all())

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
                   author=self.authors.replace(', ', ' and '),
                   year=self.datetime.year,
                   note=self.surface.description,
                   publication_url=self.get_full_url(request),
                   keywords=keywords,
                   shortname=shortname,
        )

        return s.strip()

    def _get_citation_as_biblatex(self, request):

        shortname = f"{self.surface.name}_v{self.version}".lower().replace(' ','_')
        keywords = ",".join(DEFAULT_KEYWORDS)
        if self.surface.tags.count()>0:
            keywords += ","+",".join(t.name for t in self.surface.tags.all())

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
                   author=self.authors.replace(', ', ' and '),
                   year=self.datetime.year,
                   month=self.datetime.month,
                   date=format(self.datetime, "%Y-%m-%d"),
                   note=self.surface.description,
                   url=self.get_full_url(request),
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


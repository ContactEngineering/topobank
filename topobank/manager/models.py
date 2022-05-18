"""
Basic models for the web app for handling topography data.
"""

import sys

import datacite.errors
from django.db import models
from django.shortcuts import reverse
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.core.files import File
from django.core.files.base import ContentFile
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType

from guardian.shortcuts import assign_perm, remove_perm, get_users_with_perms
import tagulous.models as tm

import PIL
import io
import logging
import math
import matplotlib
import numpy as np
import os.path
import tempfile

from bokeh.models import DataRange1d, LinearColorMapper, ColorBar
from bokeh.plotting import figure

from ..plots import configure_plot
from .utils import get_topography_reader

from topobank.users.models import User
from topobank.publication.models import Publication, DOICreationException
from topobank.users.utils import get_default_group
from topobank.analysis.models import Analysis
from topobank.analysis.utils import renew_analyses_for_subject
from topobank.manager.utils import default_storage_replace, make_dzi

from SurfaceTopography.Support.UnitConversion import get_unit_conversion_factor

_log = logging.getLogger(__name__)

MAX_LENGTH_DATAFILE_FORMAT = 15  # some more characters than currently needed, we may have sub formats in future
MAX_NUM_POINTS_FOR_SYMBOLS_IN_LINE_SCAN_PLOT = 100
SQUEEZED_DATAFILE_FORMAT = 'nc'


# Detect whether we are running within a Celery worker. This solution was suggested here:
# https://stackoverflow.com/questions/39003282/how-can-i-detect-whether-im-running-in-a-celery-worker
_IN_CELERY_WORKER_PROCESS = sys.argv and sys.argv[0].endswith('celery') and 'worker' in sys.argv


# Deprecated, but needed for migrations
def user_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/user_<id>/<filename>
    return 'topographies/user_{0}/{1}'.format(instance.surface.creator.id, filename)


class PublicationException(Exception):
    pass

class AlreadyPublishedException(PublicationException):
    pass


class NewPublicationTooFastException(PublicationException):
    def __init__(self, latest_publication, wait_seconds):
        self._latest_pub = latest_publication
        self._wait_seconds = wait_seconds

    def __str__(self):
        s = f"Latest publication for this surface is from {self._latest_pub.datetime}. "
        s += f"Please wait {self._wait_seconds} more seconds before publishing again."
        return s


class LoadTopographyException(Exception):
    pass


class PlotTopographyException(Exception):
    pass


class ThumbnailGenerationException(Exception):
    pass


class TagModel(tm.TagTreeModel):
    """This is the common tag model for surfaces and topographies.
    """

    class TagMeta:
        force_lowercase = True
        # not needed yet
        # autocomplete_view = 'manager:autocomplete-tags'


class PublishedSurfaceManager(models.Manager):
    """Manager which works on published surfaces."""

    def get_queryset(self):
        return super().get_queryset().exclude(publication__isnull=True)


class UnpublishedSurfaceManager(models.Manager):
    """Manager which works on unpublished surfaces."""

    def get_queryset(self):
        return super().get_queryset().filter(publication__isnull=True)


class SubjectMixin:
    """Extra methods common to all instances which can be subject to an analysis.
    """

    # This is needed for objects to be able to serve as subjects
    #     for analysis, because some template code uses this.
    # Probably this could be made faster by caching the result.
    # Not sure whether this should be done at compile time.
    @classmethod
    def get_content_type(cls):
        """Returns ContentType for own class."""
        return ContentType.objects.get_for_model(cls)

    def is_shared(self, with_user, allow_change=False):
        """Returns True, if this subject is shared with a given user.

        Always returns True if user is the creator of the related surface.

        :param with_user: User to test
        :param allow_change: If True, only return True if surface can be changed by given user
        :return: True or False
        """
        raise NotImplementedError()


class Surface(models.Model, SubjectMixin):
    """Physical Surface.

    There can be many topographies (measurements) for one surface.
    """
    CATEGORY_CHOICES = [
        ('exp', 'Experimental data'),
        ('sim', 'Simulated data'),
        ('dum', 'Dummy data')
    ]

    LICENSE_CHOICES = [(k, settings.CC_LICENSE_INFOS[k]['option_name']) for k in ['cc0-1.0', 'ccby-4.0', 'ccbysa-4.0']]

    name = models.CharField(max_length=80)
    creator = models.ForeignKey(User, on_delete=models.CASCADE)
    description = models.TextField(blank=True)
    category = models.TextField(choices=CATEGORY_CHOICES, null=True, blank=False)  # TODO change in character field
    tags = tm.TagField(to=TagModel)
    analyses = GenericRelation(Analysis, related_query_name='surface',
                               content_type_field='subject_type',
                               object_id_field='subject_id')

    objects = models.Manager()
    published = PublishedSurfaceManager()
    unpublished = UnpublishedSurfaceManager()

    class Meta:
        ordering = ['name']
        permissions = (
            ('share_surface', 'Can share surface'),
            ('publish_surface', 'Can publish surface'),
        )

    def __str__(self):
        s = self.name
        if self.is_published:
            s += f" (version {self.publication.version})"
        return s

    @property
    def label(self):
        return str(self)

    def get_absolute_url(self):
        return reverse('manager:surface-detail', kwargs=dict(pk=self.pk))

    def num_topographies(self):
        return self.topography_set.count()

    def to_dict(self):
        """Create dictionary for export of metadata to json or yaml.

        Does not include topographies. They can be added like this:

         surface_dict = surface.to_dict()
         surface_dict['topographies'] = [t.to_dict() for t in surface.topography_set.order_by('name')]

        The publication URL will be based on the official contact.engineering URL.

        Returns:
            dict
        """
        d = {'name': self.name,
             'category': self.category,
             'creator': {'name': self.creator.name, 'orcid': self.creator.orcid_id},
             'description': self.description,
             'tags': [t.name for t in self.tags.order_by('name')],
             'is_published': self.is_published,
             }
        if self.is_published:
            d['publication'] = {
                'url': self.publication.get_full_url(),
                'license': self.publication.get_license_display(),
                'authors': self.publication.get_authors_string(),
                'version': self.publication.version,
                'date': str(self.publication.datetime.date()),
                'doi_url': self.publication.doi_url or '',
                'doi_state': self.publication.doi_state or '',
            }
        return d

    def is_shared(self, with_user, allow_change=False):
        """Returns True, if this surface is shared with a given user.

        Always returns True if user is the creator.

        :param with_user: User to test
        :param allow_change: If True, only return True if surface can be changed by given user
        :return: True or False
        """
        result = with_user.has_perm('view_surface', self)
        if result and allow_change:
            result = with_user.has_perm('change_surface', self)
        return result

    def share(self, with_user, allow_change=False):
        """Share this surface with a given user.

        :param with_user: user to share with
        :param allow_change: if True, also allow changing the surface
        """
        assign_perm('view_surface', with_user, self)
        if allow_change:
            assign_perm('change_surface', with_user, self)

        #
        # Request all standard analyses to be available for that user
        #
        _log.info("After sharing surface %d with user %d, requesting all standard analyses..", self.id, with_user.id)
        from topobank.analysis.models import AnalysisFunction
        from topobank.analysis.utils import request_analysis
        analysis_funcs = AnalysisFunction.objects.all()
        for topo in self.topography_set.all():
            for af in analysis_funcs:
                request_analysis(with_user, af, topo)  # standard arguments

    def unshare(self, with_user):
        """Remove share on this surface for given user.

        If the user has no permissions, nothing happens.

        :param with_user: User to remove share from
        """
        for perm in ['view_surface', 'change_surface']:
            if with_user.has_perm(perm, self):
                remove_perm(perm, with_user, self)

    def deepcopy(self):
        """Creates a copy of this surface with all topographies and meta data.

        The database entries for this surface and all related
        topographies are copied, therefore all meta data.
        All files will be copied.

        References to instruments will not be copied.

        The automated analyses will be triggered for this new surface.

        Returns
        -------
        The copy of the surface.

        """
        # Copy of the surface entry
        # (see https://docs.djangoproject.com/en/2.2/topics/db/queries/#copying-model-instances)

        copy = Surface.objects.get(pk=self.pk)
        copy.pk = None
        copy.tags = self.tags.get_tag_list()
        copy.save()

        for topo in self.topography_set.all():
            new_topo = topo.deepcopy(copy)
            # we pass the surface here because there is a constraint that (surface_id + topography name)
            # must be unique, i.e. a surface should never have two topographies of the same name,
            # so we can't set the new surface as the second step
        copy.renew_analyses()

        _log.info("Created deepcopy of surface %s -> surface %s", self.pk, copy.pk)
        return copy

    def set_publication_permissions(self):
        """Sets all permissions as needed for publication.

        - removes edit, share and delete permission from everyone
        - add read permission for everyone
        """
        # Remove edit, share and delete permission from everyone
        users = get_users_with_perms(self)
        for u in users:
            for perm in ['publish_surface', 'share_surface', 'change_surface', 'delete_surface']:
                remove_perm(perm, u, self)

        # Add read permission for everyone
        assign_perm('view_surface', get_default_group(), self)

        from guardian.shortcuts import get_perms
        # TODO for unknown reasons, when not in Docker, the published surfaces are still changeable
        # Here "remove_perm" does not work. We do not allow this. See GH 704.
        if 'change_surface' in get_perms(self.creator, self):
            raise PublicationException("Withdrawing permissions for publication did not work!")

    def publish(self, license, authors):
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
        if self.is_published:
            raise AlreadyPublishedException()

        latest_publication = Publication.objects.filter(original_surface=self).order_by('version').last()
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
        copy = self.deepcopy()

        try:
            copy.set_publication_permissions()
        except PublicationException as exc:
            # see GH 704
            _log.error(f"Could not set permission for copied surface to publish .. deleting copy of surface {self.pk}.")
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
        pub = Publication.objects.create(surface=copy, original_surface=self,
                                         authors_json=authors,
                                         license=license,
                                         version=version,
                                         publisher=self.creator,
                                         publisher_orcid_id=self.creator.orcid_id)

        #
        # Try to create DOI - if this doesn't work, rollback
        #
        if settings.PUBLICATION_DOI_MANDATORY:
            try:
                pub.create_doi()
            except DOICreationException as exc:
                _log.error("DOI creation failed, reason: %s", exc)
                _log.warning("Cannot create publication with DOI, deleting publication instance.")
                pub.delete()
                raise PublicationException(f"Cannot create DOI, reason: {exc}") from exc
        else:
            _log.info("Skipping creation of DOI, because it is not configured as mandatory.")

        _log.info(f"Published surface {self.name} (id: {self.id}) " + \
                  f"with license {license}, version {version}, authors '{authors}'")
        _log.info(f"Direct URL of publication: {pub.get_absolute_url()}")
        _log.info(f"DOI name of publication: {pub.doi_name}")

        return pub

    @property
    def is_published(self):
        """Returns True, if a publication for this surface exists.
        """
        return hasattr(self, 'publication')  # checks whether the related object surface.publication exists

    def renew_analyses(self, include_topographies=True):
        """Renew analyses related to this surface.

        This includes analyses
        - with any of its topographies as subject  (if also_topographies=True)
        - with this surfaces as subject
        This is done in that order.
        """
        if include_topographies:
            _log.info("Regenerating analyses of topographies of surface %d..", self.pk)
            for topo in self.topography_set.all():
                topo.renew_analyses()
        _log.info("Regenerating analyses directly related to surface %d..", self.pk)
        renew_analyses_for_subject(self)


def _upload_path_for_datafile(instance, filename):
    return f'{instance.storage_prefix}/raw/{filename}'


def _upload_path_for_squeezed_datafile(instance, filename):
    return f'{instance.storage_prefix}/nc/{filename}'


def _upload_path_for_thumbnail(instance, filename):
    return f'{instance.storage_prefix}/thumbnail/{filename}'


class Topography(models.Model, SubjectMixin):
    """Topography Measurement of a Surface.
    """

    # TODO After upgrade to Django 2.2, use constraints: https://docs.djangoproject.com/en/2.2/ref/models/constraints/
    class Meta:
        ordering = ['measurement_date', 'pk']
        unique_together = (('surface', 'name'),)

    LENGTH_UNIT_CHOICES = [
        ('km', 'kilometers'),
        ('m', 'meters'),
        ('mm', 'millimeters'),
        ('µm', 'micrometers'),
        ('nm', 'nanometers'),
        ('Å', 'angstrom'),
    ]

    HAS_UNDEFINED_DATA_DESCRIPTION = {
        None: 'contact.engineering could not (yet) determine if this topography has undefined data points.',
        True: 'The dataset has undefined/missing data points.',
        False: 'No undefined/missing data found.'
    }

    FILL_UNDEFINED_DATA_MODE_NOFILLING = 'do-not-fill'
    FILL_UNDEFINED_DATA_MODE_HARMONIC = 'harmonic'

    FILL_UNDEFINED_DATA_MODE_CHOICES = [
        (FILL_UNDEFINED_DATA_MODE_NOFILLING, 'Do not fill undefined data points'),
        (FILL_UNDEFINED_DATA_MODE_HARMONIC, 'Interpolate undefined data points with harmonic functions'),
    ]

    DETREND_MODE_CHOICES = [
        ('center', 'No detrending, but subtract mean height'),
        ('height', 'Remove tilt'),
        ('curvature', 'Remove curvature and tilt'),
    ]

    INSTRUMENT_TYPE_UNDEFINED = 'undefined'
    INSTRUMENT_TYPE_MICROSCOPE_BASED = 'microscope-based'
    INSTRUMENT_TYPE_CONTACT_BASED = 'contact-based'

    INSTRUMENT_TYPE_CHOICES = [
        (INSTRUMENT_TYPE_UNDEFINED, 'Instrument of unknown type - all data considered as reliable'),
        (INSTRUMENT_TYPE_MICROSCOPE_BASED, 'Microscope-based instrument with known resolution'),
        (INSTRUMENT_TYPE_CONTACT_BASED, 'Contact-based instrument with known tip radius'),
    ]

    verbose_name = 'measurement'
    verbose_name_plural = 'measurements'

    #
    # Descriptive fields
    #
    surface = models.ForeignKey('Surface', on_delete=models.CASCADE)
    name = models.CharField(max_length=80)
    creator = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    measurement_date = models.DateField()
    description = models.TextField(blank=True)
    tags = tm.TagField(to=TagModel)
    analyses = GenericRelation(Analysis, related_query_name='topography',
                               content_type_field='subject_type',
                               object_id_field='subject_id')

    #
    # Fields related to raw data
    #
    datafile = models.FileField(max_length=250,
                                upload_to=_upload_path_for_datafile)  # currently upload_to not used in forms
    datafile_format = models.CharField(max_length=MAX_LENGTH_DATAFILE_FORMAT,
                                       null=True, default=None, blank=True)
    data_source = models.IntegerField()
    # Django documentation discourages the use of null=True on a CharField. I'll use it here
    # nevertheless, because I need this values as argument to a function where None has
    # a special meaning (autodetection of format). If I would use an empty string
    # as proposed in the docs, I would have to implement extra logic everywhere the field
    # 'datafile_format' is used.

    # All data is also stored in a 'squeezed' format for faster loading and processing
    # This is probably netCDF3. Scales and detrend has already been applied here.
    squeezed_datafile = models.FileField(
        max_length=260,
        upload_to=_upload_path_for_squeezed_datafile,
        null=True)

    #
    # Fields with physical meta data
    #
    size_editable = models.BooleanField(default=False)
    size_x = models.FloatField()
    size_y = models.FloatField(null=True)  # null for line scans

    unit_editable = models.BooleanField(default=False)
    unit = models.TextField(choices=LENGTH_UNIT_CHOICES)

    height_scale_editable = models.BooleanField(default=False)
    height_scale = models.FloatField(default=1)

    has_undefined_data = models.BooleanField(null=True, default=None)  # default is undefined
    fill_undefined_data_mode = models.TextField(choices=FILL_UNDEFINED_DATA_MODE_CHOICES,
                                                default=FILL_UNDEFINED_DATA_MODE_NOFILLING)

    detrend_mode = models.TextField(choices=DETREND_MODE_CHOICES, default='center')

    resolution_x = models.IntegerField(null=True)  # null for line scans TODO really?
    resolution_y = models.IntegerField(null=True)  # null for line scans

    bandwidth_lower = models.FloatField(null=True, default=None)  # in meters
    bandwidth_upper = models.FloatField(null=True, default=None)  # in meters

    is_periodic = models.BooleanField(default=False)

    #
    # Fields about instrument and its parameters
    #
    instrument_name = models.CharField(max_length=200, blank=True)
    instrument_type = models.TextField(choices=INSTRUMENT_TYPE_CHOICES, default=INSTRUMENT_TYPE_UNDEFINED)
    instrument_parameters = models.JSONField(default=dict, blank=True)

    #
    # Other fields
    #
    thumbnail = models.ImageField(
        null=True,
        upload_to=_upload_path_for_thumbnail)

    #
    # Methods
    #
    def save(self, *args, **kwargs):
        # `save` is overriden here because `storage_prefix` does not exists before the model instance has been written
        # to the database (and the `id` becomes available).
        if self.id is None:
            datafile = self.datafile
            squeezed_datafile = self.squeezed_datafile
            thumbnail = self.thumbnail
            # Since we do not have an id yet, we cannot store the file
            self.datafile = None
            self.squeezed_datafile = None
            self.thumbnail = None
            super().save(*args, **kwargs)
            # Now we have an id, so we can now save the files
            self.datafile = datafile
            self.squeezed_datafile = squeezed_datafile
            self.thumbnail = thumbnail
            kwargs.update(dict(update_fields=['datafile', 'squeezed_datafile', 'thumbnail'],
                               force_insert=False, force_update=True))  # The next save must be an update
        super().save(*args, **kwargs)

    def __str__(self):
        return "Topography '{0}' from {1}".format(self.name, self.measurement_date)

    @property
    def label(self):
        """Return a string which can be used in the UI.
        """
        return self.name

    @property
    def has_squeezed_datafile(self):
        """If True, a squeezed data file can be retrieved via self.squeezed_datafile"""
        return bool(self.squeezed_datafile)

    @property
    def has_thumbnail(self):
        """If True, a thumbnail can be retrieved via self.thumbnail"""
        return bool(self.thumbnail)

    @property
    def storage_prefix(self):
        """Return prefix used for storage.

        Looks like a relative path to a directory.
        If storage is on filesystem, the prefix should correspond
        to a real directory.
        """
        if self.id is None:
            raise RuntimeError('This `Topography` does not have an id yet; the storage prefix is not yet known.')
        return f"topographies/{self.id}"

    def get_absolute_url(self):
        """URL of detail page for this topography."""
        return reverse('manager:topography-detail', kwargs=dict(pk=self.pk))

    def cache_key(self):
        """Used for caching topographies avoiding reading datafiles again when interpreted in the same way"""
        return f"topography-{self.id}-channel-{self.data_source}"

    def is_shared(self, with_user, allow_change=False):
        """Returns True, if this topography is shared with a given user.

        Just returns whether the related surface is shared with the user
        or not.

        :param with_user: User to test
        :param allow_change: If True, only return True if topography can be changed by given user
        :return: True or False
        """
        return self.surface.is_shared(with_user, allow_change=allow_change)

    def topography(self, allow_cache=True, allow_squeezed=True):
        """Return a SurfaceTopography.Topography/UniformLineScan/NonuniformLineScan instance.

        This instance is guaranteed to

        - have a 'unit' property
        - have a size: .physical_sizes
        - have been scaled and detrended with the saved parameters

        It has not necessarily a pipeline with all these steps
        and a 'detrend_mode` attribute.

        This is only always the case
        if allow_squeezed=False. In this case the returned instance
        was regenerated from the original file with additional steps
        applied.

        If allow_squeezed=True, the returned topography may be read
        from a cached file which scaling and detrending already applied.

        Parameters
        ----------
        allow_cache: bool
            If True (default), the instance is allowed to get the
            topography from cache if available. If not, the topography
            in cache is rewritten.

        allow_squeezed: bool
            If True (default), the instance is allowed to be generated
            from a squeezed datafile which is not the original datafile.
            This is often faster then the original file format.
        """
        if not _IN_CELERY_WORKER_PROCESS and self.size_y is not None:
            _log.warning('You are requesting to load a (2D) topography and you are not within in a Celery worker '
                         'process. This operation is potentially slow and may require a lot of memory - do not use '
                         '`Topography.topography` within the main Django server!')

        cache_key = self.cache_key()

        #
        # Try to get topography from cache if possible
        #
        topo = cache.get(cache_key) if allow_cache else None
        if topo is None:
            # Build dictionary with instrument information from database... this may override data provided by the
            # topography reader
            info = {
                'instrument': {
                    'name': self.instrument_name,
                    'type': self.instrument_type,
                    'parameters': self.instrument_parameters,
                }
            }

            if allow_squeezed:
                try:
                    # If we are allowed to use a squeezed version, create one if not already happened
                    # (also needed for downloads/analyses, so this is saved in the database)
                    if not self.has_squeezed_datafile:
                        from topobank.taskapp.tasks import renew_squeezed_datafile
                        renew_squeezed_datafile.delay(self.id)
                        # this is now done in background, we load the original files instead for minimal delay
                    else:
                        #
                        # Okay, we can use the squeezed datafile, it's already there.
                        #
                        toporeader = get_topography_reader(self.squeezed_datafile, format=SQUEEZED_DATAFILE_FORMAT)
                        topo = toporeader.topography(info=info)
                        # In the squeezed format, these things are already applied/included:
                        # unit, scaling, detrending, physical sizes
                        # so don't need to provide them to the .topography() method
                        _log.info(f"Using squeezed datafile instead of original datafile for topography id {self.id}.")
                except Exception as exc:
                    _log.error(f"Could not create squeezed datafile for topography with id {self.id}. "
                               "Using original file instead.")
                    topo = None

            if topo is None:
                toporeader = get_topography_reader(self.datafile, format=self.datafile_format)
                topography_kwargs = dict(channel_index=self.data_source,
                                         periodic=self.is_periodic,
                                         info=info)

                # Set size if physical size was not given in datafile
                # (see also  TopographyCreateWizard.get_form_initial)
                # Physical size is always a tuple or None.
                channel_dict = toporeader.channels[self.data_source]
                channel_physical_sizes = channel_dict.physical_sizes
                physical_sizes_is_None = channel_physical_sizes is None \
                                         or (channel_physical_sizes == (None,)) \
                                         or (channel_physical_sizes == (None, None))
                # workaround, see GH 299 in Pyco

                if physical_sizes_is_None:
                    if self.size_y is None:
                        topography_kwargs['physical_sizes'] = self.size_x,
                    else:
                        topography_kwargs['physical_sizes'] = self.size_x, self.size_y

                if self.height_scale_editable:
                    # Adjust height scale to value chosen by user
                    topography_kwargs['height_scale_factor'] = self.height_scale

                    # This is only possible and needed, if no height scale was
                    # given in the data file already.
                    # So default is to use the factor from the file.

                #
                # Set the unit, if not already given by file contents
                #
                channel_unit = channel_dict.unit
                if not channel_unit and self.unit:
                    topography_kwargs['unit'] = self.unit

                # Eventually get topography from module "SurfaceTopography" using the given keywords
                topo = toporeader.topography(**topography_kwargs)
                if self.fill_undefined_data_mode != Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING:
                    topo = topo.interpolate_undefined_data(self.fill_undefined_data_mode)
                topo = topo.detrend(detrend_mode=self.detrend_mode)

            cache.set(cache_key, topo)
            # be sure to invalidate the cache key if topography is saved again -> signals.py

        else:
            _log.info(f"Using topography from cache for id {self.id}.")

        return topo

    def renew_analyses(self):
        """Submit all analysis for this topography."""
        renew_analyses_for_subject(self)

    def to_dict(self):
        """Create dictionary for export of metadata to json or yaml"""
        result = {'name': self.name,
                  'datafile': {
                      'original': self.datafile.name,
                      'squeezed-netcdf': self.squeezed_datafile.name,
                  },
                  'data_source': self.data_source,
                  'has_undefined_data': self.has_undefined_data,
                  'fill_undefined_data_mode': self.fill_undefined_data_mode,
                  'detrend_mode': self.detrend_mode,
                  'is_periodic': self.is_periodic,
                  'creator': {'name': self.creator.name, 'orcid': self.creator.orcid_id},
                  'measurement_date': self.measurement_date,
                  'description': self.description,
                  'unit': self.unit,
                  'size': [self.size_x] if self.size_y is None else [self.size_x, self.size_y],
                  'tags': [t.name for t in self.tags.order_by('name')],
                  'instrument': {
                      'name': self.instrument_name,
                      'type': self.instrument_type,
                      'parameters': self.instrument_parameters,
                  }}
        if self.height_scale_editable:
            result['height_scale'] = self.height_scale
            # see GH 718

        return result

    def deepcopy(self, to_surface):
        """Creates a copy of this topography with all data files copied.

        Parameters
        ----------
        to_surface: Surface
            target surface

        Returns
        -------
        The copied topography.
        The reference to an instrument is not copied, it is always None.

        """

        copy = Topography.objects.get(pk=self.pk)
        copy.pk = None
        copy.surface = to_surface

        with self.datafile.open(mode='rb') as datafile:
            copy.datafile = default_storage.save(self.datafile.name, File(datafile))

        copy.tags = self.tags.get_tag_list()
        copy.save()

        return copy

    def get_thumbnail(self, width=400, height=400, cmap=None):
        """
        Make thumbnail image.

        Parameters
        ----------
        width : int, optional
            Maximum width of the thumbnail. (Default: 400)
        height : int, optional
            Maximum height of the thumbnail. (Default: 400)
        cmap : str or colormap, optional
            Color map for rendering the topography. (Default: None)

        Returns
        -------
        image : bytes-like
            Thumbnail image.
        """
        st_topo = self.topography()  # SurfaceTopography instance (=st)
        image_file = io.BytesIO()
        if st_topo.dim == 1:
            dpi = 100
            fig, ax = matplotlib.pyplot.subplots(figsize=[width / dpi, height / dpi])
            x, y = st_topo.positions_and_heights()
            ax.plot(x, y, '-')
            ax.set_axis_off()
            fig.savefig(image_file, bbox_inches='tight', dpi=100, format='png')
        elif st_topo.dim == 2:
            # Compute thumbnail size (keeping aspect ratio)
            sx, sy = st_topo.physical_sizes
            width2 = int(sx * height / sy)
            height2 = int(sy * width / sx)
            if width2 <= width:
                width = width2
            else:
                height = height2

            # Get heights and rescale to interval 0, 1
            heights = st_topo.heights()
            mx, mn = heights.max(), heights.min()
            heights = (heights - mn) / (mx - mn)
            # Get color map
            cmap = matplotlib.cm.get_cmap(cmap)
            # Convert to image
            colors = (cmap(heights.T) * 255).astype(np.uint8)
            # Remove alpha channel before writing
            PIL.Image.fromarray(colors[:, :, :3]).resize((width, height)).save(image_file, format='png')
        else:
            raise RuntimeError(f"Don't know how to create thumbnail for topography of dimension {st_topo.dim}.")
        return image_file

    def get_plot(self, thumbnail=False):
        """Return bokeh plot.

        Parameters
        ----------
        thumbnail
            boolean, if True, return a reduced plot suitable for a thumbnail

        Returns
        -------

        """
        try:
            st_topo = self.topography()  # SurfaceTopography instance (=st)
        except Exception as exc:
            raise LoadTopographyException("Can't load topography.") from exc

        if st_topo.dim == 1:
            try:
                return self._get_1d_plot(st_topo, reduced=thumbnail)
            except Exception as exc:
                raise PlotTopographyException("Error generating 1D plot for topography.") from exc
        elif st_topo.dim == 2:
            try:
                return self._get_2d_plot(st_topo, reduced=thumbnail)
            except Exception as exc:
                raise PlotTopographyException("Error generating 2D plot for topography.") from exc
        else:
            raise PlotTopographyException("Can only plot 1D or 2D topographies, this has {} dimensions.".format(
                st_topo.dim
            ))

    def _get_1d_plot(self, st_topo, reduced=False):
        """Calculate 1D line plot of topography (line scan).

        :param st_topo: SurfaceTopography.Topography instance
        :return: bokeh plot
        """
        x, y = st_topo.positions_and_heights()

        x_range = DataRange1d(bounds='auto')
        y_range = DataRange1d(bounds='auto')

        TOOLTIPS = """
            <style>
                .bk-tooltip>div:not(:first-child) {{display:none;}}
                td.tooltip-varname {{ text-align:right; font-weight: bold}}
            </style>

            <table>
              <tr>
                <td class="tooltip-varname">x</td>
                <td>:</td>
                <td>@x {}</td>
              </tr>
              <tr>
                <td class="tooltip-varname">height</td>
                <td>:</td>
                <td >@y {}</td>
              </tr>
            </table>
        """.format(self.unit, self.unit)

        if reduced:
            toolbar_location = None
        else:
            toolbar_location = 'above'

        plot = figure(x_range=x_range, y_range=y_range,
                      x_axis_label=f'Position ({self.unit})',
                      y_axis_label=f'Height ({self.unit})',
                      tooltips=TOOLTIPS,
                      toolbar_location=toolbar_location)

        show_symbols = y.shape[0] <= MAX_NUM_POINTS_FOR_SYMBOLS_IN_LINE_SCAN_PLOT

        if reduced:
            line_kwargs = dict(line_width=3)
        else:
            line_kwargs = dict()

        plot.line(x, y, **line_kwargs)
        if show_symbols:
            plot.circle(x, y)

        configure_plot(plot)
        if reduced:
            plot.xaxis.visible = False
            plot.yaxis.visible = False
            plot.grid.visible = False

        plot.toolbar.logo = None

        return plot

    def _get_2d_plot(self, st_topo, reduced=False):
        """Calculate 2D image plot of topography.

        :param st_topo: SurfaceTopography.Topography instance
        :return: bokeh plot
        """
        heights = st_topo.heights()

        topo_size = st_topo.physical_sizes
        # x_range = DataRange1d(start=0, end=topo_size[0], bounds='auto')
        # y_range = DataRange1d(start=0, end=topo_size[1], bounds='auto')
        x_range = DataRange1d(start=0, end=topo_size[0], bounds='auto', range_padding=5)
        y_range = DataRange1d(start=topo_size[1], end=0, flipped=True, range_padding=5)

        color_mapper = LinearColorMapper(palette="Viridis256", low=heights.min(), high=heights.max())

        TOOLTIPS = [
            ("Position x", "$x " + self.unit),
            ("Position y", "$y " + self.unit),
            ("Height", "@image " + self.unit),
        ]
        colorbar_width = 50

        aspect_ratio = topo_size[0] / topo_size[1]
        frame_height = 500
        frame_width = int(frame_height * aspect_ratio)

        if frame_width > 1200:  # rule of thumb, scale down if too wide
            frame_width = 1200
            frame_height = int(frame_width / aspect_ratio)

        if reduced:
            toolbar_location = None
        else:
            toolbar_location = 'above'

        plot = figure(x_range=x_range,
                      y_range=y_range,
                      frame_width=frame_width,
                      frame_height=frame_height,
                      # sizing_mode='scale_both',
                      # aspect_ratio=aspect_ratio,
                      match_aspect=True,
                      x_axis_label=f'x ({self.unit})',
                      y_axis_label=f'y ({self.unit})',
                      # tools=[PanTool(),BoxZoomTool(match_aspect=True), "save", "reset"],
                      tooltips=TOOLTIPS,
                      toolbar_location=toolbar_location)

        configure_plot(plot)
        if reduced:
            plot.xaxis.visible = False
            plot.yaxis.visible = False

        # we need to rotate the height data in order to be compatible with image in Gwyddion
        plot.image([np.rot90(heights)], x=0, y=topo_size[1],
                   dw=topo_size[0], dh=topo_size[1], color_mapper=color_mapper)
        # the anchor point of (0,topo_size[1]) is needed because the y range is flipped
        # in order to have the origin in upper left like in Gwyddion

        plot.toolbar.logo = None

        if not reduced:
            colorbar = ColorBar(color_mapper=color_mapper,
                                label_standoff=12,
                                location=(0, 0),
                                width=colorbar_width,
                                title=f"height ({self.unit})")
            plot.add_layout(colorbar, 'right')

        return plot

    def _renew_images(self):
        """Renew thumbnail and deep zoom images.

        Returns
        -------
        None
        """
        image_file = self.get_thumbnail()

        # Remove old thumbnail
        self.thumbnail.delete()

        # Save the contents of in-memory file in Django image field
        self.thumbnail.save(
            'thumbnail.png',
            ContentFile(image_file.getvalue()),
        )

        if self.size_y is not None:
            # This is a topography (map), we need to create a Deep Zoom Image
            make_dzi(self.topography(), f'{self.storage_prefix}/dzi')

    def renew_images(self, none_on_error=True):
        """Renew thumbnail field.

        Parameters
        ----------
        none_on_error: bool
            If True (default), sets thumbnail to None if there are any errors.
            If False, exceptions have to be caught outside.

        Returns
        -------
        None

        Raises
        ------
        ThumbnailGenerationException
        """
        try:
            self._renew_images()
        except Exception as exc:
            if none_on_error:
                self.thumbnail = None
                self.save()
                _log.warning(f"Problems while generating thumbnail for topography {self.id}: {exc}. "
                             "Saving <None> instead.")
                import traceback
                _log.warning(f"Traceback: {traceback.format_exc()}")
            else:
                raise ThumbnailGenerationException from exc

    def _renew_bandwidth_cache(self, st_topo=None):
        if st_topo is None:
            st_topo = self.topography()
        if st_topo.unit is not None:
            bandwidth_lower, bandwidth_upper = st_topo.bandwidth()
            fac = get_unit_conversion_factor(st_topo.unit, 'm')
            self.bandwidth_lower = fac * bandwidth_lower
            self.bandwidth_upper = fac * bandwidth_upper

    def renew_squeezed_datafile(self):
        """Renew squeezed datafile file."""
        _log.info(f"Renewing squeezed datafile for topography {self.id}..")
        with tempfile.NamedTemporaryFile() as tmp:
            # Reread topography from original file
            st_topo = self.topography(allow_cache=False, allow_squeezed=False)

            # Check whether original data file has undefined data point and update database accordingly.
            # (We never load the topography so we don't know this until here. `has_undefined_data` can be
            # undefined.)
            parent_topo = st_topo
            while hasattr(parent_topo, 'parent_topography'):
                parent_topo = parent_topo.parent_topography
            self.has_undefined_data = parent_topo.has_undefined_data
            if not self.has_undefined_data:
                self.fill_undefined_data_mode = Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING

            # Cache bandwidth for bandwidth plot in database. Data is stored in units of meter.
            self._renew_bandwidth_cache(st_topo)

            # Write and upload NetCDF file
            st_topo.to_netcdf(tmp.name)
            # Delete old squeezed file
            self.squeezed_datafile.delete()
            # Upload new squeezed file
            dirname, basename = os.path.split(self.datafile.name)
            orig_stem, orig_ext = os.path.splitext(basename)
            squeezed_name = f'{orig_stem}-squeezed.nc'
            self.squeezed_datafile.save(squeezed_name, File(open(tmp.name, mode='rb')))
            self.save()

    def get_undefined_data_status(self):
        """Get human-readable description about status of undefined data as string."""
        s = self.HAS_UNDEFINED_DATA_DESCRIPTION[self.has_undefined_data]
        if self.fill_undefined_data_mode == Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING:
            s += ' No correction of undefined data is performed.'
        elif self.fill_undefined_data_mode == Topography.FILL_UNDEFINED_DATA_MODE_HARMONIC:
            s += ' Undefined/missing values are filled in with values obtained from a harmonic interpolation.'
        return s

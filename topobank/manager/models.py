from django.db import models
from django.shortcuts import reverse
from django.core.cache import cache
from django.db import transaction

from guardian.shortcuts import assign_perm, remove_perm

from .utils import get_topography_reader

from topobank.users.models import User

def user_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/user_<id>/<filename>
    return 'topographies/user_{0}/{1}'.format(instance.surface.creator.id, filename)

class Surface(models.Model):
    """Physical Surface.

    There can be many topographies (measurements) for one surface.
    """
    CATEGORY_CHOICES = [
        ('exp', 'Experimental data'),
        ('sim', 'Simulated data'),
        ('dum', 'Dummy data')
    ]

    name = models.CharField(max_length=80)
    creator = models.ForeignKey(User, on_delete=models.CASCADE)
    description = models.TextField(blank=True)
    category = models.TextField(choices=CATEGORY_CHOICES, null=True, blank=False) #  TODO change in character field

    class Meta:
        ordering = ['name']
        permissions = (
            ('share_surface', 'Can share surface'),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('manager:surface-detail', kwargs=dict(pk=self.pk))

    def num_topographies(self):
        return self.topography_set.count()

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
        from topobank.analysis.models import AnalysisFunction
        from topobank.analysis.utils import request_analysis
        auto_analysis_funcs = AnalysisFunction.objects.filter(automatic=True)
        for topo in self.topography_set.all():
            for af in auto_analysis_funcs:
                request_analysis(with_user, af, topo) # standard arguments


    def unshare(self, with_user):
        """Remove share on this surface for given user.

        If the user has no permissions, nothing happens.

        :param with_user: User to remove share from
        """
        for perm in ['view_surface', 'change_surface']:
            if with_user.has_perm(perm, self):
                remove_perm(perm, with_user, self)


class Topography(models.Model):
    """Topography Measurement of a Surface.
    """

    # TODO After upgrade to Django 2.2, use contraints: https://docs.djangoproject.com/en/2.2/ref/models/constraints/
    class Meta:
        unique_together = (('surface', 'name'),)

    LENGTH_UNIT_CHOICES = [
        # (None, '(unknown)') # TODO should this be allowed?
        ('km', 'kilometers'),
        ('m','meters'),
        ('mm', 'millimeters'),
        ('µm', 'micrometers'),
        ('nm', 'nanometers'),
        ('Å', 'angstrom'),
    ]

    DETREND_MODE_CHOICES = [
        ('center', 'No detrending, but substract mean height'),
        ('height', 'Remove tilt'),
        ('curvature', 'Remove curvature'),
    ]

    verbose_name_plural = 'topographies'

    #
    # Descriptive fields
    #
    surface = models.ForeignKey('Surface', on_delete=models.CASCADE)
    name = models.CharField(max_length=80)
    creator = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    measurement_date = models.DateField()
    description = models.TextField(blank=True)

    #
    # Fields related to raw data
    #
    datafile = models.FileField(max_length=250, upload_to=user_directory_path)  # currently upload_to not used in forms
    data_source = models.IntegerField()

    #
    # Fields with physical meta data
    #
    size_editable = models.BooleanField(default=False)
    size_x = models.FloatField()
    size_y = models.FloatField(null=True) # null for line scans

    unit_editable = models.BooleanField(default=False)
    unit = models.TextField(choices=LENGTH_UNIT_CHOICES)

    height_scale_editable = models.BooleanField(default=False)
    height_scale = models.FloatField(default=1)

    detrend_mode = models.TextField(choices=DETREND_MODE_CHOICES, default='center')

    resolution_x = models.IntegerField(null=True) # null for line scans
    resolution_y = models.IntegerField(null=True) # null for line scans

    #
    # Methods
    #
    def __str__(self):
        return "Topography '{0}' from {1}".format(\
            self.name, self.measurement_date)

    def get_absolute_url(self):
        return reverse('manager:topography-detail', kwargs=dict(pk=self.pk))

    def cache_key(self):
        return f"topography-{self.id}-channel-{self.data_source}"

    def topography(self):
        """Return a PyCo Topography/Line Scan instance.

        This instance is guaranteed to

        - have an info dict with 'unit' key: .info['unit']
        - have a size: .physical_sizes
        - scaled and detrended with the saved parameters

        """
        cache_key = self.cache_key()

        #
        # Try to get topography from cache if possible
        #
        topo = cache.get(cache_key)
        if topo is None:
            toporeader = get_topography_reader(self.datafile)
            topography_kwargs = dict(channel=self.data_source)

            # Set size if physical size was not given in datafile
            # (see also  TopographyCreateWizard.get_form_initial)
            # Physical size is always a tuple.
            if self.size_editable: # TODO: could be removed in favor of "channel_dict['physical_sizes'] is None"
                if self.size_y is None:
                    topography_kwargs['physical_sizes'] = self.size_x,
                else:
                    topography_kwargs['physical_sizes'] = self.size_x, self.size_y

            if self.height_scale_editable:
                # Adjust height scale to value chosen by user
                topography_kwargs['height_scale_factor'] = self.height_scale

            # Eventually get PyCo topography using the given keywords
            topo = toporeader.topography(**topography_kwargs)
            topo = topo.detrend(detrend_mode=self.detrend_mode, info=dict(unit=self.unit))

            cache.set(cache_key, topo)
            # be sure to invalidate the cache key if topography is saved again -> signals.py

        return topo

    def renew_analyses(self):
        """Submit all automatic analysis for this topography.

        Before make sure to delete all analyses for same topography,
        they all can be wrong if this topography changed.

        TODO Maybe also renew all already existing analyses with different parameters?

        Implementation Note:

        This method cannot be easily used in a post_save signal,
        because the pre_delete signal deletes the datafile and
        this also then triggers "renew_analyses".
        """
        from topobank.analysis.utils import submit_analysis
        from topobank.analysis.models import AnalysisFunction, Analysis
        from guardian.shortcuts import get_users_with_perms

        auto_analysis_funcs = AnalysisFunction.objects.filter(automatic=True)

        # collect users which are allowed to view analyses
        users = get_users_with_perms(self.surface)

        def submit_all(instance=self):
            for af in auto_analysis_funcs:
                Analysis.objects.filter(function=af, topography=instance).delete()
                submit_analysis(users, af, instance)

        transaction.on_commit(lambda: submit_all(self))

    def to_dict(self):
        """Create dictionary for export of metadata to json or yaml"""
        return {'name': self.name,
                'data_source': self.data_source,
                'creator': {'name': self.creator.name, 'orcid': self.creator.orcid_id},
                'measurement_date': self.measurement_date,
                'description': self.description,
                'unit': self.unit,
                'height_scale': self.height_scale,
                'size': (self.size_x, self.size_y)}

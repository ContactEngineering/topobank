from django.db import models, transaction
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFill


from .utils import TopographyFile, selected_topographies
from topobank.users.models import User

def user_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/user_<id>/<filename>
    return 'topographies/user_{0}/{1}'.format(instance.surface.user.id, filename)

class Surface(models.Model):
    """Physical Surface.

    There can be many topographies (measurements) for one surface.
    """
    name = models.CharField(max_length=80)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    description = models.TextField(blank=True)

    def thumbnail(self):
        # TODO probably thumbnail of surface should show a plot with summary, but not a random topography!

        if self.topography_set.count() > 0:
            return self.topography_set.first().surface_thumbnail
        else:
            return None

    def num_topographies(self):
        return self.topography_set.count()

class Topography(models.Model):
    """Topography Measurement of a Surface.
    """

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
        ('center', 'No detrending'),
        ('height', 'Remove tilt'),
        ('curvature', 'Remove curvature'),
    ]

    verbose_name_plural = 'topographies'

    #
    # Description fields
    #
    surface = models.ForeignKey('Surface', on_delete=models.CASCADE)
    name = models.CharField(max_length=80)

    datafile = models.FileField(upload_to=user_directory_path) # currently upload_to not used in forms
    data_source = models.IntegerField()
    measurement_date = models.DateField()
    description = models.TextField(blank=True)

    #
    # Fields with physical meta data
    #
    size_editable = models.BooleanField(default=False)
    size_x = models.IntegerField()
    size_y = models.IntegerField(null=True) # null for line scans

    size_unit_editable = models.BooleanField(default=False) # also applies to height_unit
    size_unit = models.TextField(choices=LENGTH_UNIT_CHOICES) # TODO allow null?

    height_scale_editable = models.BooleanField(default=False)
    height_scale = models.FloatField(default=1)
    height_unit = models.TextField(choices=LENGTH_UNIT_CHOICES) # TODO remove

    detrend_mode = models.TextField(choices=DETREND_MODE_CHOICES, default='center')

    #
    # Fields for image creation
    #
    image = models.ImageField(default='topographies/not_available.png') # TODO Check if needed
    thumbnail = ImageSpecField(source='image',
                               processors=[ResizeToFill(100,100)],
                               format='JPEG',
                               options={'quality': 60}) # TODO Check if needed
    resolution_x = models.IntegerField(null=True) # null for line scans
    resolution_y = models.IntegerField(null=True) # null for line scans

    #
    # Methods
    #
    def __str__(self):
        return "Topography '{0}' from {1}".format(\
            self.name, self.measurement_date)

    def topography(self):
        """Return a PyCo Topography/Line Scan instance.

        This instance is guaranteed to

        - have an info dict with 'unit' key: .info['unit']
        - have a size: .size
        - scaled and detrended with the saved parameters

        """
        topofile = TopographyFile(self.datafile.path) # assuming the datafile is stored on disk

        topo = topofile.topography(int(self.data_source))
        # TODO int() is a fix for SQLite which cannot return real int?? remove for PG

        #
        # Now prepare topography using the parameters from database
        #

        # set size if physical size was not given in datafile
        # (see also  TopographyCreateWizard.get_form_initial)

        if self.size_editable:
            if self.size_y is None:
                topo.size = self.size_x, # size is now always a tuple
            else:
                topo.size = self.size_x, self.size_y

        topo = topo.scale(self.height_scale).detrend(detrend_mode=self.detrend_mode)

        topo.info['unit'] = self.size_unit  # TODO what about height unit

        return topo

    def submit_images_creation(self): # TODO remove if not needed for thumbnails
        from .utils import create_topography_images
        transaction.on_commit(lambda: create_topography_images.delay(self.id))

    def submit_automated_analyses(self):
        """Submit all automatic analysis for this Topography.
        """
        from topobank.taskapp.tasks import submit_analysis
        from topobank.analysis.models import AnalysisFunction

        auto_analysis_funcs = AnalysisFunction.objects.filter(automatic=True)

        def submit_all(instance=self):
            for af in auto_analysis_funcs:
                submit_analysis(af, instance)

        transaction.on_commit(lambda: submit_all(self))




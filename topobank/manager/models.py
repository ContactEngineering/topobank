from django.db import models, transaction
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFill

import matplotlib.pyplot as plt
import io

from .utils import TopographyFile, selected_topographies
from topobank.users.models import User

def user_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/user_<id>/<filename>
    return 'topographies/user_{0}/{1}'.format(instance.user.id, filename)

class Surface(models.Model):
    """Physical Surface.

    There can be many topographies (measurements) for one surface.
    """
    name = models.CharField(max_length=80)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    # TODO add more meta data

    def thumbnail(self):
        # TODO what if there is not topography yet?

        if self.topography_set.count() > 0:
            return self.topography_set.first().surface_thumbnail
        else:
            return None

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

    surface = models.ForeignKey('Surface', on_delete=models.CASCADE)

    name = models.CharField(max_length=80)

    datafile = models.FileField(upload_to=user_directory_path)
    data_source = models.IntegerField()
    measurement_date = models.DateField()
    description = models.TextField(blank=True)

    size_x = models.IntegerField()
    size_y = models.IntegerField()
    size_unit = models.TextField(choices=LENGTH_UNIT_CHOICES) # TODO allow null?

    height_scale = models.FloatField(default=1)
    height_unit = models.TextField(choices=LENGTH_UNIT_CHOICES) # TODO remove

    detrend_mode = models.TextField(choices=DETREND_MODE_CHOICES, default='center')

    surface_image = models.ImageField(default='topographies/not_available.png')
    surface_thumbnail = ImageSpecField(source='surface_image',
                                       processors=[ResizeToFill(100,100)],
                                       format='JPEG',
                                       options={'quality': 60})

    verbose_name_plural = 'topographies'

    def __str__(self):
        return "Topography '{0}' from {1}".format(\
            self.name, self.measurement_date)

    def update_surface_image(self):
        """Create image for surface for web interface.

        :return: None
        """
        topo = self.topography()

        arr = topo.array()

        fig = plt.figure()
        ax = fig.add_subplot(1,1,1)
        ax.pcolormesh(arr)

        # save figure in a memory buffer and use this as source for image field
        buffer = io.BytesIO()
        fig.savefig(buffer, format='png')
        self.surface_image.save('images/surface-{}.png'.format(self.pk), buffer, save=False)
        # save=False in order to avoid recursion
        # TODO later also create image in a task

    def topography(self):
        """Return PyCo Topography instance"""
        topofile = TopographyFile(self.datafile.path)  # TODO use datafile.open here

        topo = topofile.topography(int(self.data_source))
        # TODO int() is a fix for SQLite which cannot return real int?? remove for PG

        topo.unit = self.size_unit
        topo.parent_topography.coeff = self.height_scale
        topo.size = self.size_x, self.size_y

        topo.detrend_mode = self.detrend_mode

        return topo



@receiver(pre_save, sender=Topography)
def update_surface_image(sender, instance, **kwargs):
    # TODO also calculate the image in a task
    # instance.update_surface_image()
    # TODO commenting out here because of error "main thread is not in main loop" when creating test database
    pass

@receiver(post_save, sender=Topography)
def compute_surface_properties(sender, instance, **kwargs):
    #
    # Submit here all functions which should be called by default
    # on new topographies
    #
    # These imports are done here in order to avoid import conflicts
    from topobank.taskapp.tasks import submit_analysis
    from topobank.analysis.models import AnalysisFunction

    auto_analysis_funcs = AnalysisFunction.objects.filter(automatic=True)

    def submit_all(instance=instance):
        for af in auto_analysis_funcs:
            submit_analysis(af, instance)

    transaction.on_commit(lambda: submit_all(instance))



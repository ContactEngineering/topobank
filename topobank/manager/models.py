from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFill

import matplotlib.pyplot as plt
import io

from .utils import TopographyFile
from topobank.users.models import User

def user_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/user_<id>/<filename>
    return 'topographies/user_{0}/{1}'.format(instance.user.id, filename)

class Topography(models.Model):

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

    name = models.CharField(max_length=80)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    datafile = models.FileField(upload_to=user_directory_path)
    data_source = models.IntegerField()
    measurement_date = models.DateField()
    description = models.TextField(blank=True)

    size_x = models.IntegerField()
    size_y = models.IntegerField()
    size_unit = models.TextField(choices=LENGTH_UNIT_CHOICES) # TODO allow null?

    height_scale = models.FloatField(default=1)
    height_unit = models.TextField(choices=LENGTH_UNIT_CHOICES) # TODO allow null?

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
        topofile = TopographyFile(self.datafile.path) # TODO use datafile.open here

        surface = topofile.surface(int(self.data_source))
        # int() is a fix for SQLite which cannot return real int??
        arr = surface.profile()

        nx, ny = arr.shape

        fig = plt.figure()
        ax = fig.add_subplot(1,1,1)
        ax.pcolormesh(arr)

        # save figure in a memory buffer and use this as source for image field
        buffer = io.BytesIO()
        fig.savefig(buffer, format='png')
        self.surface_image.save('images/surface-{}.png'.format(self.pk), buffer, save=False)

        # save=False in order to avoid recursion

@receiver(pre_save, sender=Topography)
def update_surface_image(sender, instance, **kwargs):
    instance.update_surface_image()


from django.db import models

from topobank.users.models import User

def user_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/user_<id>/<filename>
    return 'topographies/user_{0}/{1}'.format(instance.user.id, filename)

class Topography(models.Model):

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    datafile = models.FileField(upload_to=user_directory_path)
    measurement_date = models.DateField()
    description = models.TextField(blank=True)

    verbose_name_plural = 'topographies'

    def __str__(self):
        return "Topography measured on {0}, file {1}".format(\
            self.measurement_date, self.datafile.name)

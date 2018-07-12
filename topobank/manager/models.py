from django.db import models

from topobank.users.models import User

def user_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/user_<id>/<filename>
    return 'topographies/user_{0}/{1}'.format(instance.user.id, filename)

class Topography(models.Model):

    name = models.CharField(max_length=80)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    datafile = models.FileField(upload_to=user_directory_path)
    measurement_date = models.DateField()
    description = models.TextField(blank=True)

    verbose_name_plural = 'topographies'

    def __str__(self):
        return "Topography '{0}' from {1}".format(\
            self.name, self.measurement_date)

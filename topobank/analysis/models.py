from django.db import models

class Analysis(models.Model):

    topography = models.ForeignKey('manager.Topography',
                                   on_delete=models.CASCADE)

    task_id = models.CharField(max_length=155, unique=True)

    args = models.BinaryField() # for pickle
    kwargs = models.BinaryField() # for pickle

    # TODO save reference to analysis function

    result = models.BinaryField(null=True, default=None) # for pickle

    successful = models.BooleanField(default=False)
    failed = models.BooleanField(default=False)

    # TODO save traceback in case of exeption

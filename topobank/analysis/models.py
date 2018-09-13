from django.db import models
from topobank.manager.models import Topography

class Analysis(models.Model):

    PENDING = 'pe'
    STARTED = 'st'
    RETRY = 're'
    FAILURE = 'fa'
    SUCCESS = 'su'

    TASK_STATE_CHOICES = (
        (PENDING, 'pending'),
        (STARTED, 'started'),
        (RETRY, 'retry'),
        (FAILURE, 'failure'),
        (SUCCESS, 'success'),
    )

    function = models.ForeignKey('AnalysisFunction', on_delete=models.CASCADE)

    topography = models.ForeignKey(Topography,
                                   on_delete=models.CASCADE)

    args = models.BinaryField() # for pickle TODO rename to "other_args", since topography is first arg?
    kwargs = models.BinaryField() # for pickle

    task_id = models.CharField(max_length=155, unique=True, null=True)
    task_state = models.CharField(max_length=7,
                                  choices=TASK_STATE_CHOICES)

    result = models.BinaryField(null=True, default=None)  # for pickle, in case of failure, can be Exception instance

class AnalysisFunction(models.Model):
    name = models.CharField(max_length=80, help_text="A human-readable name.", unique=True)
    pyfunc = models.CharField(max_length=256,
                              help_text="Name of Python function in topobank.analysis.functions")
    # this reference to python function may change in future
    automatic  = models.BooleanField(default=False,
                                     help_text="If set, this analysis is automatically triggered for new topographies.")


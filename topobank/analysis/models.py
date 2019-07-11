from django.db import models
import pickle

from topobank.manager.models import Topography
import topobank.analysis.functions as functions_module

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

    kwargs = models.BinaryField() # for pickle

    task_id = models.CharField(max_length=155, unique=True, null=True)
    task_state = models.CharField(max_length=7,
                                  choices=TASK_STATE_CHOICES)

    start_time = models.DateTimeField(null=True)
    end_time = models.DateTimeField(null=True)

    result = models.BinaryField(null=True, default=None)  # for pickle, in case of failure, can be Exception instance

    def __str__(self):
        return "Task {} with state {}".format(self.task_id, self.get_task_state_display())

    def duration(self):
        """Returns duration of computation or None if not finished yet.

        Does not take into account the queue time.

        :return: Returns datetime.timedelta or None
        """
        if self.end_time is None:
            return None

        return self.end_time-self.start_time

    def get_kwargs_display(self):
        return str(pickle.loads(self.kwargs))

    @property
    def result_obj(self):
        return pickle.loads(self.result) if self.result else None

    @property
    def storage_prefix(self):
        return "analyses/{}/".format(self.id)

class AnalysisFunction(models.Model):
    name = models.CharField(max_length=80, help_text="A human-readable name.", unique=True)
    pyfunc = models.CharField(max_length=256,
                              help_text="Name of Python function in {}".format(functions_module.__name__))
    # this reference to python function may change in future
    automatic  = models.BooleanField(default=False,
                                     help_text="If set, this analysis is automatically triggered for new topographies.")

    def __str__(self):
        return self.name

    @property
    def python_function(self):
        return getattr(functions_module, self.pyfunc)

    def eval(self, *args, **kwargs):
        """Call appropriate python function.
        """
        return self.python_function(*args, **kwargs)

    @property
    def card_view_flavor(self):
        return self.python_function.card_view_flavor

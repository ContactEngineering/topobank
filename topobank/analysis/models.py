from django.db import models

import pickle

from topobank.manager.models import Topography
from topobank.users.models import User
import topobank.analysis.functions as functions_module


class Dependency(models.Model):
    """A dependency of analysis results, e.g. "PyCo", "topobank"
    """
    # this is used with "import":
    import_name = models.CharField(max_length=30, unique=True)

    def __str__(self):
        return self.import_name

class Version(models.Model):
    """
    A specific version of a dependency.
    Part of a configuration.
    """
    dependency = models.ForeignKey(Dependency, on_delete=models.CASCADE)

    major = models.SmallIntegerField()
    minor = models.SmallIntegerField()
    micro = models.SmallIntegerField(null=True)

    # the following can be used to indicate that this
    # version should not be used any more / or the analyses
    # should be recalculated
    # valid = models.BooleanField(default=True)

    # TODO After upgrade to Django 2.2, use contraints: https://docs.djangoproject.com/en/2.2/ref/models/constraints/
    class Meta:
        unique_together = (('dependency', 'major', 'minor', 'micro'),)

    def number_as_string(self):
        x = f"{self.major}.{self.minor}"
        if self.micro is not None:
            x += f".{self.micro}"
        return x

    def __str__(self):
        return f"{self.dependency} {self.number_as_string()}"



class Configuration(models.Model):
    """For keeping track which versions were used for an analysis.
    """
    valid_since = models.DateTimeField(auto_now_add=True)
    # pyco_version = models.CharField(max_length=20, help_text="PyCo version.")

    versions = models.ManyToManyField(Version)

    def __str__(self):
        versions = [ str(v) for v in self.versions.all()]
        return f"Valid since: {self.valid_since}, versions: {versions}"


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

    # According to github #208, each user should be able to see analysis with parameters chosen by himself
    users = models.ManyToManyField(User)

    kwargs = models.BinaryField()  # for pickle

    task_id = models.CharField(max_length=155, unique=True, null=True)
    task_state = models.CharField(max_length=7,
                                  choices=TASK_STATE_CHOICES)

    start_time = models.DateTimeField(null=True)
    end_time = models.DateTimeField(null=True)

    result = models.BinaryField(null=True, default=None)  # for pickle, in case of failure, can be Exception instance

    configuration = models.ForeignKey(Configuration, null=True, on_delete=models.SET_NULL)

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

class AnalysisCollection(models.Model):
    name = models.CharField(max_length=160)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    # notfiy = models.BooleanField(default=False)
    analyses = models.ManyToManyField(Analysis)
    combined_task_state = models.CharField(max_length=7,
                                           choices=Analysis.TASK_STATE_CHOICES)

    # We have a manytomany field, because an analysis could be part of multiple collections.
    # This happens e.g. if the user presses "recalculate" several times and
    # one analysis becomes part in each of these requests.




"""
Models related to analyses.
"""
from django.db import models
from django.db.models import CheckConstraint, Q, UniqueConstraint
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

import inspect
import pickle

from topobank.manager.models import Topography, Surface
from topobank.users.models import User
from .registry import ImplementationMissingException


class Dependency(models.Model):
    """A dependency of analysis results, e.g. "SurfaceTopography", "topobank"
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

    topography = models.ForeignKey(Topography, null=True,
                                   on_delete=models.CASCADE)
    surface = models.ForeignKey(Surface, null=True,
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

    @property
    def subject(self):
        if self.topography:
            return self.topography
        else:
            # This does only work with the constraint that
            # only one field of topography and surface is
            # allowed to be NULL
            return self.surface

    class Meta:
        # exactly one field of topography + surface must be NULL
        constraints = [CheckConstraint(name='unique_subject',
                                       check=(Q(topography__isnull=True) & Q(surface__isnull=False)) | \
                                             (Q(topography__isnull=False) & Q(surface__isnull=True)))]


# class AnalysisSubject(models.Model):
#     """Subject of an analysis, e.g. a surface or topography"""
#     content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
#     object_id = models.PositiveIntegerField()
#     content_object = GenericForeignKey('content_type', 'object_id')
#
#     def __str__(self):
#         return f"{self.content_type.name}(id={self.object_id})"


class AnalysisFunction(models.Model):
    """Represents an analysis function from a user perspective.

    Examples:
        - name: 'Height distribution', card_view_flavor='plot'
        - name: 'Contact Mechanics', card_view_flavor='contact mechanics'

    These functions are referenced by the analyses. Each function "knows"
    how to find the appropriate implementation for given arguments.
    """
    SIMPLE = 'simple'
    PLOT = 'plot'
    POWER_SPECTRUM = 'power spectrum'
    CONTACT_MECHANICS = 'contact mechanics'
    RMS_TABLE = 'rms table'
    CARD_VIEW_FLAVOR_CHOICES = [
        (SIMPLE, 'Simple display of the results as raw data structure'),
        (PLOT, 'Display results in a plot with multiple datasets'),
        (POWER_SPECTRUM, 'Display results in a plot suitable for power spectrum'),
        (CONTACT_MECHANICS, 'Display suitable for contact mechanics including special widgets'),
        (RMS_TABLE, 'Display a table with RMS values.')
    ]

    name = models.CharField(max_length=80, help_text="A human-readable name.", unique=True)
    card_view_flavor = models.CharField(max_length=50, default=SIMPLE, choices=CARD_VIEW_FLAVOR_CHOICES)

    def __str__(self):
        return self.name

    def _implementation(self, subject_type):
        """Return implementation for given subject type.

        Parameters
        ----------
        subject_type: type
            Type of first argument of analysis function, e.g.
            `topobank.manager.models.Topography` or `topobank.manager.models.Surface`.

        Returns
        -------
        AnalysisFunctionImplementation instance
        """
        try:
            st = subject_type.__name__.lower()[0]  # TODO use generic content types, intermediate solution
            impl = self.implementations.get(subject_type=st)
        except AnalysisFunctionImplementation.DoesNotExist as exc:
            raise ImplementationMissingException(self.name, subject_type)
        return impl

    def python_function(self, subject_type):
        """Return function for given first argument type.

        Parameters
        ----------
        subject_type: type
            Type of first argument of analysis function, e.g.
            `topobank.manager.models.Topography` or `topobank.manager.models.Surface`.

        Returns
        -------
        Python function, where first argument must be the given type.
        """
        return self._implementation(subject_type).python_function()

    def get_default_kwargs(self, subject_type):
        """Return default keyword arguments as dict.

        Administrative arguments like
        'storage_prefix' and 'progress_recorder'
        which are common to all functions, are excluded.

        Parameters
        ----------
        subject_type: type
            Type of first argument of analysis function, e.g.
            `topobank.manager.models.Topography` or `topobank.manager.models.Surface`.

        Returns
        -------

        dict
        """
        return self._implementation(subject_type).get_default_kwargs()

    def eval(self, subject, **kwargs):
        """Call appropriate python function.

        First argument is the subject of the analysis (topography or surface),
        all other arguments are keyword arguments.
        """
        subject_type = type(subject)
        return self._implementation(subject_type).eval(subject, **kwargs)


class AnalysisFunctionImplementation(models.Model):
    """Represents an implementation of an analysis function depending on subject."""

    SUBJECT_TYPE_TOPOGRAPHY = 't'
    SUBJECT_TYPE_SURFACE = 's'

    SUBJECT_TYPE_CHOICES = [
        (SUBJECT_TYPE_TOPOGRAPHY, 'topography'),
        (SUBJECT_TYPE_SURFACE, 'surface'),
    ]

    function = models.ForeignKey(AnalysisFunction, related_name='implementations', on_delete=models.CASCADE)
    subject_type = models.CharField(max_length=1, choices=SUBJECT_TYPE_CHOICES)  # TODO use generic content types, intermediate solution
    pyfunc = models.CharField(max_length=256)  # name of Python function in functions module

    class Meta:
        constraints = [
            UniqueConstraint(fields=['function', 'subject_type'], name='distinct_implementation')
        ]

    def python_function(self):
        """Return reference to corresponding Python function."""
        import topobank.analysis.functions as functions_module
        try:
            return getattr(functions_module, self.pyfunc)
        except AttributeError as exc:
            raise ValueError(f"Cannot resolve reference to python function '{self.pyfunc}'.")

    @staticmethod
    def _get_default_args(func):
        # thanks to mgilson, his answer on SO:
        # https://stackoverflow.com/questions/12627118/get-a-function-arguments-default-value#12627202

        signature = inspect.signature(func)
        return {
            k: v.default
            for k, v in signature.parameters.items()
            if v.default is not inspect.Parameter.empty
        }

    def get_default_kwargs(self):
        """Return default keyword arguments as dict.

        Administrative arguments like
        'storage_prefix' and 'progress_recorder'
        which are common to all functions, are excluded.
        """
        dkw = self._get_default_args(self.python_function())
        if 'storage_prefix' in dkw:
            del dkw['storage_prefix']
        if 'progress_recorder' in dkw:
            del dkw['progress_recorder']
        return dkw

    def eval(self, subject, **kwargs):
        """Evaluate implementation on given subject with given arguments."""
        pyfunc = self.python_function()
        return pyfunc(subject, **kwargs)


class AnalysisCollection(models.Model):
    """A collection of analyses which belong togehter for some reason."""
    name = models.CharField(max_length=160)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    # notfiy = models.BooleanField(default=False)
    analyses = models.ManyToManyField(Analysis)
    combined_task_state = models.CharField(max_length=7,
                                           choices=Analysis.TASK_STATE_CHOICES)

    # We have a manytomany field, because an analysis could be part of multiple collections.
    # This happens e.g. if the user presses "recalculate" several times and
    # one analysis becomes part in each of these requests.


CARD_VIEW_FLAVORS = [cv for cv, _ in AnalysisFunction.CARD_VIEW_FLAVOR_CHOICES]

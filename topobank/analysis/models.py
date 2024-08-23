"""
Models related to analyses.
"""

import json

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import models
from django.utils import timezone

from ..manager.models import Surface, Tag, Topography
from ..supplib.dict import load_split_dict, store_split_dict
from ..supplib.storage import recursive_delete
from ..taskapp.models import Configuration, TaskStateModel
from ..users.models import User
from .registry import AnalysisRegistry, ImplementationMissingAnalysisFunctionException

RESULT_FILE_BASENAME = "result"


class AnalysisSubject(models.Model):
    """Analysis subject, which can be either a Tag, a Topography or a Surface"""

    tag = models.ForeignKey(Tag, null=True, blank=True, on_delete=models.CASCADE)
    topography = models.ForeignKey(
        Topography, null=True, blank=True, on_delete=models.CASCADE
    )
    surface = models.ForeignKey(
        Surface, null=True, blank=True, on_delete=models.CASCADE
    )

    @classmethod
    def create(cls, subject):
        tag = topography = surface = None
        if isinstance(subject, Tag):
            tag = subject
        elif isinstance(subject, Topography):
            topography = subject
        elif isinstance(subject, Surface):
            surface = subject
        else:
            raise ValueError(
                "`subject` argument must be of type `Tag`, `Topography` or `Surface`."
            )
        return cls.objects.create(tag=tag, topography=topography, surface=surface)

    @staticmethod
    def Q(subject):
        if isinstance(subject, Tag):
            return models.Q(subject_dispatch__tag_id=subject.id)
        elif isinstance(subject, Topography):
            return models.Q(subject_dispatch__topography_id=subject.id)
        elif isinstance(subject, Surface):
            return models.Q(subject_dispatch__surface_id=subject.id)
        else:
            raise ValueError(
                "`subject` argument must be of type `Tag`, `Topography` or `Surface`, "
                f"not {type(subject)}."
            )

    def get(self):
        if self.tag is not None:
            return self.tag
        elif self.topography is not None:
            return self.topography
        elif self.surface is not None:
            return self.surface
        else:
            raise RuntimeError(
                "Database corruption: All subjects appear to be None/null."
            )

    def save(self, *args, **kwargs):
        if (
            sum(
                [
                    self.tag is not None,
                    self.topography is not None,
                    self.surface is not None,
                ]
            )
            != 1
        ):
            raise ValidationError("Only of of tag, topography or tag can be defined.")
        super().save(*args, **kwargs)


class Analysis(TaskStateModel):
    """
    Concrete Analysis with state, function reference, arguments, and results.

    Additionally, it saves the configuration which was present when
    executing the analysis, i.e. versions of the main libraries needed.
    """

    # Actual implementation of the analysis as a Python function
    function = models.ForeignKey("AnalysisFunction", on_delete=models.CASCADE)

    # Definition of the subject
    subject_dispatch = models.OneToOneField(
        AnalysisSubject, null=True, on_delete=models.CASCADE
    )

    # User that triggered this analysis
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    # Keyword arguments passed to the Python analysis function
    kwargs = models.JSONField(default=dict)

    # Bibliography
    dois = models.JSONField(default=list)

    # Server configuration (version information)
    configuration = models.ForeignKey(
        Configuration, null=True, on_delete=models.SET_NULL
    )

    class Meta:
        verbose_name_plural = "analyses"

    def __init__(self, *args, result=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._result = result  # temporary storage
        self._result_cache = result  # cached result
        self._result_metadata_cache = None  # cached toplevel result file

    def __str__(self):
        return "Task {} with state {}".format(
            self.task_id, self.get_task_state_display()
        )

    def delete(self, *args, **kwargs):
        """
        Delete the analysis instance, including its associated task and storage files.

        This method performs the following steps:
        1. Cancels the task if it is currently running.
        2. Removes associated files from the storage backend.
        3. Deletes the database entry for the analysis instance.

        Parameters
        ----------
        *args : tuple
            Variable length argument list.
        **kwargs : dict
            Arbitrary keyword arguments.
        """
        # Cancel task (if running)
        self.cancel_task()

        # Remove files from storage
        recursive_delete(self.storage_prefix)

        # Delete database entry
        super().delete(*args, **kwargs)

    def save(self, *args, **kwargs):
        """
        Save the analysis instance to the database.

        This method performs the following steps:
        1. Sets the creation time if the instance does not have an ID.
        2. Calls the parent class's save method to save the instance.
        3. Stores the result dictionary in the storage backend if it is provided.

        Parameters
        ----------
        *args : tuple
            Variable length argument list.
        **kwargs : dict
            Arbitrary keyword arguments.
        """
        if not self.id:
            self.creation_time = timezone.now()
        super().save(*args, **kwargs)
        # If a result dict is given on input, we store it. However, we can only do this once we have an id.
        # This happens during testing.
        if self._result is not None:
            store_split_dict(self.storage_prefix, RESULT_FILE_BASENAME, self._result)
            self._result = None

    @property
    def subject(self):
        """
        Return the subject of the analysis, which can be a Tag, a Topography, or a Surface.

        Returns
        -------
        Tag, Topography, or Surface
            The subject of the analysis.
        """
        return self.subject_dispatch.get()

    @property
    def result(self):
        """
        Return the result object or None if there is nothing yet.

        This property checks if the result cache is empty. If it is, it loads the result
        from the storage backend using the storage prefix and result file basename.
        The loaded result is then cached for future access.

        Returns
        -------
        dict or None
            The result object if available, otherwise None.
        """
        if self._result_cache is None:
            self._result_cache = load_split_dict(
                self.storage_prefix, RESULT_FILE_BASENAME
            )
        return self._result_cache

    @property
    def result_metadata(self):
        """
        Return the toplevel result object without series data, i.e. the raw result.json without unsplitting it.

        This property checks if the result metadata cache is empty. If it is, it loads the metadata
        from the storage backend using the storage prefix and result file basename.
        The loaded metadata is then cached for future access.

        Returns
        -------
        dict
            The toplevel result object without series data.
        """
        if self._result_metadata_cache is None:
            self._result_metadata_cache = json.load(
                default_storage.open(
                    f"{self.storage_prefix}/{RESULT_FILE_BASENAME}.json"
                )
            )
        return self._result_metadata_cache

    @property
    def result_file_name(self):
        """Returns name of the result file in storage backend as string."""
        return f"{self.storage_prefix}/{RESULT_FILE_BASENAME}.json"

    @property
    def has_result_file(self):
        """Returns True if result file exists in storage backend, else False."""
        return default_storage.exists(self.result_file_name)

    @property
    def storage_prefix(self):
        """Return prefix used for storage.

        Looks like a relative path to a directory.
        If storage is on filesystem, the prefix should correspond
        to a real directory.
        """
        if self.id is None:
            raise RuntimeError(
                "This `Analysis` does not have an id yet; the storage prefix is not yet known."
            )
        return "analyses/{}".format(self.id)
    
    @property
    def storage_files(self):
        """Return all file names in analysis id directory.

        List of files names ['<file_prefix_name>/file'].
        If storage is on filesystem, the prefix should correspond
        to a real directory.
        """
        if self.id is None:
            raise RuntimeError('This `Analysis` does not have an id yet; the storage file names is not yet known.')
        dir_tuple = default_storage.listdir(f'analyses/{self.id}')
        file_lists = dir_tuple[1]
        return [f'{self.storage_prefix}/{file_name}' for file_name in file_lists]

    def get_related_surfaces(self):
        """Returns sequence of surface instances related to the subject of this analysis."""
        return self.subject.get_related_surfaces()

    def get_implementation(self):
        return self.function.get_implementation(
            ContentType.objects.get_for_model(self.subject)
        )

    def authorize_user(self, user):
        """Returns an exception if given user should not be able to see this analysis."""
        if not self.get_implementation().is_available_for_user(user):
            raise PermissionError(
                f"User {user} is not allowed to use this analysis function."
            )
        if not all(
            user.has_perm("view_surface", s) for s in self.get_related_surfaces()
        ):
            raise PermissionError(
                f"User {user} is not allowed to access some of the surfaces that are the subject of the analysis."
            )

    @property
    def is_topography_related(self):
        """Returns True, if the analysis subject is a topography, else False."""
        return self.subject_dispatch.topography is not None

    @property
    def is_surface_related(self):
        """Returns True, if the analysis subject is a surface, else False."""
        return self.subject_dispatch.surface is not None

    @property
    def is_tag_related(self):
        """Returns True, if the analysis subject is a tag, else False."""
        return self.subject_dispatch.tag is not None


class AnalysisFunction(models.Model):
    """Represents an analysis function from a user perspective.

    Examples:
        - name: 'Height distribution'
        - name: 'Contact mechanics'

    These functions are referenced by the analyses. Each function "knows"
    how to find the appropriate implementation for given arguments.
    """

    name = models.CharField(
        max_length=80, help_text="A human-readable name.", unique=True
    )

    def __str__(self):
        return self.name

    def get_implementation(self, subject_type):
        """Return implementation for given subject type.

        Parameters
        ----------
        subject_type: ContentType
            Type of first argument of analysis function

        Returns
        -------
        AnalysisFunctionImplementation instance

        Raises
        ------
        ImplementationMissingException
            in case the implementation is missing
        """
        return AnalysisRegistry().get_implementation(
            self.name, subject_type=subject_type
        )

    def get_python_function(self, subject_type):
        """Return function for given first argument type.

        Parameters
        ----------
        subject_type: ContentType
            Type of first argument of analysis function

        Returns
        -------
        Python function which implements the analysis, where first argument must be the given type,
        and there maybe more arguments needed.

        Raises
        ------
        ImplementationMissingException
            if implementation for given subject type does not exist
        """
        return self.get_implementation(subject_type).python_function

    def get_signature(self, subject_type):
        """Return signature of function for given first argument type.

        Parameters
        ----------
        subject_type: ContentType
            Type of first argument of analysis function

        Returns
        -------
        inspect.signature

        Raises
        ------
        ImplementationMissingException
            if implementation for given subject type does not exist
        """
        return self.get_implementation(subject_type).signature

    def get_implementation_types(self):
        """Return list of content types for which this function is implemented."""
        return AnalysisRegistry().get_implementation_types(self.name)

    def is_implemented_for_type(self, subject_type):
        """Returns True if function is implemented for given content type, else False"""
        try:
            self.get_python_function(subject_type)
        except ImplementationMissingAnalysisFunctionException:
            return False
        return True

    def is_available_for_user(self, user, models=None):
        """
        Check if this analysis function is available to the user. The function
        is available to `user` if it is available for any of the `models`
        specified.
        """
        if models is None:
            from ..manager.models import Surface, Tag, Topography

            models = set([Tag, Topography, Surface])

        is_available_to_user = False
        for model in models:
            try:
                impl = self.get_implementation(ContentType.objects.get_for_model(model))
                is_available_to_user |= impl.is_available_for_user(user)
            except ImplementationMissingAnalysisFunctionException:
                pass
        return is_available_to_user

    def get_default_kwargs(self, subject_type):
        """Return default keyword arguments as dict.

        Administrative arguments like
        'storage_prefix' and 'progress_recorder'
        which are common to all functions, are excluded.

        Parameters
        ----------
        subject_type: ContentType
            Type of first argument of analysis function

        Returns
        -------

        dict
        """
        return self.get_implementation(subject_type).default_kwargs

    def eval(self, subject, **kwargs):
        """Call appropriate python function.

        First argument is the subject of the analysis (topography or surface),
        all other arguments are keyword arguments.
        """
        if subject is None:
            raise ValueError(
                f"Cannot evaluate analysis function '{self.name}' with None as subject."
            )
        try:
            subject_type = ContentType.objects.get_for_model(subject)
        except Exception:
            raise ValueError(f"Cannot find content type for subject '{subject}'.")
        return self.get_implementation(subject_type).eval(subject, **kwargs)

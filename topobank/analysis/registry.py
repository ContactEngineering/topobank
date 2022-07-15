"""
Registry for collection analysis functions.
"""
import inspect
import logging

from django.db import models
from django.db.models import UniqueConstraint

from ..utils import Singleton

from django.contrib.contenttypes.models import ContentType

_log = logging.getLogger(__name__)

# Analysis Result Types ('art' parameter)
ART_GENERIC = 'generic'
ART_SERIES = 'plot'


class RegistryException(Exception):
    """Generic exception for problems while handling analysis functions."""
    pass


class UnknownAnalysisFunctionException(RegistryException):
    """No analysis function with given name known."""

    def __init__(self, name):
        self._name = name

    def __str__(self):
        return f"No analysis function defined with name '{self._name}'."


class UnimplementedAnalysisFunctionException(RegistryException):
    """No implementation for analysis function with given name registered."""

    def __init__(self, name):
        self._name = name

    def __str__(self):
        return f"No implementation has been registered for analysis function '{self._name}'."


class AlreadyRegisteredAnalysisFunctionException(RegistryException):  # TODO replace with  AlreadyRegisteredException ?
    """An implementation of an analysis function has already been defined."""

    def __init__(self, name, subject_app_label, subject_model):
        self._name = name
        self._subject_app_label = subject_app_label
        self._subject_model = subject_model

    def __str__(self):
        return f"An implementation for analysis function '{self._name}' with subject type " +\
               f"'{self._subject_model}' (app '{self._subject_app_label}') has already been defined."


class AlreadyRegisteredException(RegistryException):
    """A function has already been registered for the given key."""

    def __init__(self, key):
        self._key = key

    def __str__(self):
        return f"An implementation for key '{self._key}' has already been defined."


class ImplementationMissingAnalysisFunctionException(RegistryException):
    """An analysis function implementation was not found for given subject type."""

    def __init__(self, name, subject_app_label, subject_model):
        self._name = name
        self._subject_app_label = subject_app_label
        self._subject_model = subject_model

    def __str__(self):
        return f"Implementation for analysis function '{self._name}' for " \
               f"subject type '{self._subject_model}' (app '{self._subject_app_label}')" +\
               " not found."


class InconsistentAnalysisResultTypeException(RegistryException):
    """Analysis result type for an analysis function is not unique."""

    def __init__(self, name, curr_art, new_art):
        self._name = name
        self._curr_art = curr_art
        self._new_art = new_art

    def __str__(self):
        return f"An implementation for analysis function '{self._name}' was given with "+\
               f"analysis result type '{self._new_art}', but before "+\
               f"analysis result type '{self._curr_art}' was defined. It should be unique."


class UnknownCardViewFlavorException(RegistryException):
    """Card view flavor for an analysis function is not known."""

    def __init__(self, key):
        self._key = key

    def __str__(self):
        return f"An unknown card view flavor was given in key '{self._key}' while registering a function."


class UnknownKeyException(RegistryException):
    """A key was requested which is not known."""

    def __init__(self, key):
        self._key = key

    def __str__(self):
        return f"Key '{self._key}' is unknown."


class AnalysisRegistry(metaclass=Singleton):
    """Central register for analysis related code.

    This singleton is used by the register_* decorators
    below in order to collect analysis function implementations,
    download functions and card view classes on startup.

    Checks for consistency so nothing get overwritten
    during registration process.
    """
    def __init__(self):
        self._implementations = {}  # TODO maybe rename to analysis function implementation
        # key: (art, name, subject_app_label, subject_model)
        #      where
        #      art: str, analysis result type
        #      name: str, Function name in UI,
        #      subject_app_label: str, application label for subject_model
        #      subject_model: str, e.g. "topography" or "surface",
        #                     should correspond to first argument of analysis function implementations
        #                     and to model class name
        # value: reference to implementation of analysis function

        self._download_functions = {}
        # key: (art, spec, file_format) where
        #
        #      art: str, analysis result type
        #      spec: str, short name for what should be downloaded, e.g. 'results'
        #      file_format: str, e.g. 'txt' or 'xlsx'
        # value: reference to implementation of download function

        self._card_view_classes = {}
        # key: art: str, analysis result type
        # value: reference to card view class

        self._art_by_function_name = {}
        # key: str, art
        # value: analysis function name in UI

        self._analysis_result_types = set()
        # analysis result types (aka arts) which have been seen so far

    ###################################################################
    # Handling of analysis function implementations
    ###################################################################
    def add_implementation(self, art, name, subject_app_label, func):
        """Register implementation of an analysis function.

        Depending on the name of the first argument of the given function,
        this implementation is registered as a function being called for topographies
        or surfaces.

        You can use the @register_implementation decorator in order to
        add an implementation to the registry.

        Parameters
        ----------
        art: str
            Analysis result type
        name: str
            Function name in the UI
        subject_app_label: str
            Label of app in which the given subject type is expected (e.g. "manager")
        func: function
            Python function which implements the analysis function
        """

        # Find out name of first argument
        func_spec = inspect.getfullargspec(func)
        subject_model = func_spec.args[0]

        _log.info(f"Adding analysis function implementation for art: {art}, function name: {name}, "
                  f"app_label: {subject_app_label}, subject_type: {subject_model}..")

        #
        # For a given function name, the card view flavor should be unique
        #
        if name in self._art_by_function_name:
            curr_art = self._art_by_function_name[name]
            if curr_art != art:
                raise InconsistentAnalysisResultTypeException(name, curr_art, art)
        self._art_by_function_name[name] = art

        #
        # Do not get subject type of function from database, this is too early.
        # The database might not have been setup yet.
        # We just save the subject_model instead.
        # Django itself has a cache for content types, we don't have to implement an own one.
        #

        #
        # Check key
        #
        key = (art, name, subject_app_label, subject_model)
        # We are using the subject_model here because otherwise we have problems
        # during test setup if we use Contenttypes here (not fully ready)

        # Each implementation should only be defined once
        if key in self._implementations:
            raise AlreadyRegisteredAnalysisFunctionException(art, name, subject_app_label, subject_model)

        #
        # Okay, add this implementation
        #
        self._analysis_result_types.add(art)

        impl = AnalysisFunctionImplementation(func)
        self._implementations[key] = impl

    def get_implementation(self, name, subject_type):
        """Return AnalysisFunctionImplementation for given analysis function and subject type.

        Parameters
        ----------
        name: str
            Name of analysis function.
        subject_type: ContentType
            ContentType of subject (first argument of implementing function)

        Returns
        -------
        AnalysisFunctionImplementation instance
        """
        subject_app_label = subject_type.app_label
        subject_model = subject_type.model
        try:
            art = self._art_by_function_name[name]
            return self._implementations[(art, name, subject_app_label, subject_model)]
        except KeyError as exc:
            raise ImplementationMissingAnalysisFunctionException(name, subject_app_label, subject_model) from exc

    def get_analysis_function_names(self):
        """Returns function names as list."""
        return list(set(name for art, name, subject_app_label, subject_model in self._implementations.keys()))

    def get_implementation_types(self, name):
        """Returns function names as list."""
        return list(set(ContentType.objects.get_by_natural_key(subject_app_label, subject_model)
                        for art, n, subject_app_label, subject_model in self._implementations.keys() if n==name))

    def get_analysis_result_type_for_function_name(self, requested_name):
        """Return analysis result type for given function name."""
        for art, name, subject_app_label, subject_model in self._implementations.keys():
            if requested_name == name:
                return art
        raise ValueError(f"No function registered with given name {requested_name}.")

    def sync_analysis_functions(self, cleanup=False):
        """Make sure all analysis functions are represented in database.

        It's recommended to run this with cleanup=True if an analysis
        function should be removed.

        Parameters
        ----------

        cleanup: bool
            If True, delete all analysis functions for which no implementations exist
            and also delete all analyses related to those functions.
            Be careful, will delete existing analyses.
        """
        from .models import AnalysisFunction, Analysis

        counts = dict(
            funcs_updated=0,
            funcs_created=0,
            funcs_deleted=0,
        )

        #
        # Ensure all analysis functions needed to exist in database
        #
        function_names_used = self.get_analysis_function_names()

        for name in function_names_used:
            art = self.get_analysis_result_type_for_function_name(name)
            func, created = AnalysisFunction.objects.update_or_create(defaults=dict(card_view_flavor=art),
                                                                      name=name)
            if created:
                counts['funcs_created'] += 1
            else:
                counts['funcs_updated'] += 1

        #
        # Optionally delete all analysis functions which are no longer needed
        #
        for func in AnalysisFunction.objects.all():
            if func.name not in function_names_used:
                _log.info(f"Function '{func.name}' is no longer used in the code.")
                dangling_analyses = Analysis.objects.filter(function=func)
                num_analyses = dangling_analyses.filter(function=func).count()
                _log.info(f"There are still {num_analyses} analyses for this function.")
                if cleanup:
                    _log.info("Deleting those..")
                    dangling_analyses.delete()
                    func.delete()
                    _log.info(f"Deleted function '{func.name}' and all its analyses.")
                    counts['funcs_deleted'] += 1

        return counts

    ###################################################################
    # Handling of download functions
    ###################################################################
    def add_download_function(self, art, spec, file_format, func):
        """Register implementation of a download function.

        You can use the @register_download_function decorator in order to
        add an implementation to the registry.

        Parameters
        ----------
        art: str
            Analysis result type
        spec: str
            Short name for what should be downloaded, e.g. 'results'
        file_format: str
            File format provided by the iven function
        func: function
            Python function which implements the download function
        """

        key = (art, spec, file_format)

        # Each implementation should only be defined once
        if key in self._download_functions:
            raise AlreadyRegisteredException(key)

        self._analysis_result_types.add(art)

        self._download_functions[key] = func

    def get_download_function(self, art, spec, file_format):
        """Return Python function for given parameters.

        Parameters
        ----------
        art: str
            Analysis result type
        spec: str
            Short name for what should be downloaded, e.g. 'results'
        file_format: str
            File format provided by the iven function

        Returns
        -------
        Reference to Python function of form

           download_func(request, analyses)

        where request: HttpRequest, analyses: sequence of Analysis objects

        The referenced function returns a HttpResponse with a file download.
        """
        key = (art, spec, file_format)

        try:
            return self._download_functions[key]
        except KeyError as exc:
            raise UnknownKeyException(key) from exc

    ###################################################################
    # Handling of card view classes
    ###################################################################
    def add_card_view_class(self, art, cls):
        """Add a card view class for given analysis result type.

        Parameters
        ----------
        art: str
            Analysis result type. Use 'generic' to define a view which is
            used as fallback when no other view was configured.
        """
        if art in self._card_view_classes:
            raise AlreadyRegisteredException(art)
        self._card_view_classes[art] = cls
        self._analysis_result_types.add(art)

    def get_card_view_class(self, art):
        """Get card view class for given analysis type."""
        try:
            return self._card_view_classes[art]
        except KeyError as exc:
            if 'generic' in self._card_view_classes:
                return self._card_view_classes['generic']
            raise UnknownKeyException(art) from exc


######################################################################################
# Decorators for registering functions and classes (used from plugins)
######################################################################################
def register_implementation(art="simple", name=None, subject_app_label="manager"):
    """Decorator for marking a function as implementation for an analysis function.

    Parameters
    ----------
    art: str
        Analysis result type.
    name: str
        UI name of analysis function.
    subject_app_label: str
        App label where the subject is defined as model, e.g. "manager"
    """
    def register_decorator(func):
        """
        :param func: function to be registered, first arg must be a "topography" or "surface"
        :return: decorated function

        Depending on the name of the first argument, you get either a Topography
        or a Surface instance. The model is searched only for the given subject_app_label.
        """
        registry = AnalysisRegistry()  # singleton
        registry.add_implementation(art, name, subject_app_label, func)
        return func

    return register_decorator


def register_download_function(art, spec, file_format):
    """Decorator for marking a function as a download function.

    Parameters
    ----------
    art: str
        Analysis result type.
    spec: str
            Short name for what should be downloaded, e.g. 'results'
    file_format: str
        File format provided by the given function
    """
    def register_decorator(func):
        registry = AnalysisRegistry()  # singleton
        registry.add_download_function(art, spec, file_format, func)
        return func

    return register_decorator


def register_card_view_class(art):
    """Decorator for marking a class as a card view.

    Parameters
    ----------
    art: str
        Analysis result type.
    func: function
        Python function which implements the download function
    """
    def register_decorator(cls):
        registry = AnalysisRegistry()  # singleton
        registry.add_card_view_class(art, cls)
        return cls

    return register_decorator


class AnalysisFunctionImplementation:
    """Represents an implementation of an analysis function depending on subject."""

    def __init__(self, pyfunc):
        """

        Parameters
        ----------
        pyfunc: function
        """
        self._pyfunc = pyfunc

    def python_function(self):
        """Return reference to corresponding Python function."""
        return self._pyfunc

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
        dkw = self._get_default_args(self._pyfunc)
        if 'storage_prefix' in dkw:
            del dkw['storage_prefix']
        if 'progress_recorder' in dkw:
            del dkw['progress_recorder']
        return dkw

    def eval(self, subject, **kwargs):
        """Evaluate implementation on given subject with given arguments."""
        return self.python_function()(subject, **kwargs)

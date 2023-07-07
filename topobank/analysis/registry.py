"""
Registry for collection analysis functions.

Each function has an `visualization_type`, determines the type of standardized
results an analysis function produces. This standardization applies to
which files are placed in the S3 under the `data` route of the analysis.

The frontend selects a visualization ui app based on the vizui type, that
expects certain files to be present. This means the same vizui type is
visualized by the same frontend app, but it may be produced by a different
analysis function.

As an example, analyses producing simply x-y plots (height distribution,
autocorrelationm, power spectrum) have the same visualization type and are
visualized using the same frontend app.

Frontend apps are implemented as Vue.js components.
"""

import inspect
import logging

from ..utils import Singleton

from django.contrib.contenttypes.models import ContentType

_log = logging.getLogger(__name__)


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

    def __init__(self, visualization_type, name, subject_app_name, subject_model):
        self._visualization_type = visualization_type
        self._name = name
        self._subject_app_name = subject_app_name
        self._subject_model = subject_model

    def __str__(self):
        return f"An implementation for analysis function '{self._name}' " \
               f"(visualization type: {self._visualization_type}) with subject type " \
               f"'{self._subject_model}' (app '{self._subject_app_name}') has already been defined."


class DefaultKwargsDifferException(RegistryException):
    def __init__(self, name, subject_app_name1, subject_model1, default_kwargs1, subject_app_name2, subject_model2,
                 default_kwargs2):
        self._name = name
        self._subject_app_name1 = subject_app_name1
        self._subject_model1 = subject_model1
        self._default_kwargs1 = default_kwargs1
        self._subject_app_name2 = subject_app_name2
        self._subject_model2 = subject_model2
        self._default_kwargs2 = default_kwargs2

    def __str__(self):
        return f"Analysis function '{self._name}' has already been registered for model " \
               f"'{self._subject_app_name1}|{self._subject_model1}' with default keyword arguments " \
               f"'{self._default_kwargs1}. The implementation for '{self._subject_app_name2}|{self._subject_model2}' " \
               f"has different default keyword arguments of '{self._default_kwargs2}."


class AlreadyRegisteredException(RegistryException):
    """A function has already been registered for the given key."""

    def __init__(self, key):
        self._key = key

    def __str__(self):
        return f"An implementation for key '{self._key}' has already been defined."


class ImplementationMissingAnalysisFunctionException(RegistryException):
    """An analysis function implementation was not found for given subject type."""

    def __init__(self, name, subject_app_name, subject_model):
        self._name = name
        self._subject_app_name = subject_app_name
        self._subject_model = subject_model

    def __str__(self):
        return f"Implementation for analysis function '{self._name}' for " \
               f"subject type '{self._subject_model}' (app '{self._subject_app_name}')" +\
               " not found."


class InconsistentAnalysisResultTypeException(RegistryException):
    """visualization type for an analysis function is not unique."""

    def __init__(self, name, curr_visualization_type, new_visualization_type):
        self._name = name
        self._curr_visualization_type = curr_visualization_type
        self._new_visualization_type = new_visualization_type

    def __str__(self):
        return f"An implementation for analysis function '{self._name}' was given with "+\
               f"visualization type '{self._new_visualization_type}', but before "+\
               f"visualization type '{self._curr_visualization_type}' was defined. It should be unique."


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
        self._analysis_functions = {}
        # key: (name, subject_app_name, subject_model)
        #      where
        #      name: str, Unique function name,
        #      subject_app_name: str, application name for subject_model
        #      subject_model: str, e.g. "topography" or "surface",
        #                     should correspond to first argument of analysis function implementations
        #                     and to model class name
        # value: reference to implementation of analysis function

        self._download_functions = {}
        # key: (visualization_type, spec, file_format) where
        #
        #      visualization_type: str, visualization type
        #      spec: str, short name for what should be downloaded, e.g. 'results'
        #      file_format: str, e.g. 'txt' or 'xlsx'
        # value: reference to implementation of download function

        self._app_name = {}
        # key: visualization_type: str, visualization type
        # value: Name of Django app/plugin where the visualization resides

        self._visualization_type_by_function_name = {}
        # key: name: str, Unique function name,
        # value: visualization_type: str, visualization type

    ###################################################################
    # Handling of analysis function implementations
    ###################################################################
    def add_implementation(self, visualization_app_name, visualization_type, name, subject_app_name, func):
        """
        Register implementation of an analysis function.

        Depending on the name of the first argument of the given function,
        this implementation is registered as a function being called for topographies
        or surfaces.

        You can use the @register_implementation decorator in order to
        add an implementation to the registry.

        Parameters
        ----------
        visualization_app_name : str
            Application name (plugin name) that provides the analysis
        visualization_type: str
            visualization type
        name: str
            Function name in the UI
        subject_app_name: str
            Label of app in which the given subject type is expected (e.g. "manager")
        func: function
            Python function which implements the analysis function
        """

        # Construct implementation
        impl = AnalysisFunctionImplementation(func)
        subject_model = impl.get_subject_model()

        _log.debug(f"Adding implementation for analysis function '{name}' for subject "
                   f"'{subject_app_name}|{subject_model}' with visualization type '{visualization_type}'.")

        # Idiot check: For a given function name, the card view flavor should be unique
        if name in self._visualization_type_by_function_name:
            curr_visualization_type = self._visualization_type_by_function_name[name]
            if curr_visualization_type != visualization_type:
                raise InconsistentAnalysisResultTypeException(name, curr_visualization_type, visualization_type)
        else:
            self._visualization_type_by_function_name[name] = visualization_type

        # Idiot check: Make sure same visualization types reside in the same app
        if visualization_type in self._app_name:
            if self._app_name[visualization_type] != visualization_app_name:
                raise RuntimeError(f"Visualization type '{visualization_type}' has already been registered within "
                                   f"Django app '{self._app_name[visualization_type]}'. Cannot register another "
                                   f"implementation within a different app '{visualization_app_name}'.")
        else:
            self._app_name[visualization_type] = visualization_app_name

        #
        # Do not get subject type of function from database, this is too early.
        # The database might not have been setup yet.
        # We just save the subject_model instead.
        # Django itself has a cache for content types, we don't have to implement an own one.
        #

        # Construct key
        key = (name, subject_app_name, subject_model)
        # We are using the subject_model here because otherwise we have problems
        # during test setup if we use Contenttypes here (not fully ready)

        default_kwargs = impl.default_kwargs
        for (_name, _subject_app_name, _subject_model), _impl in self._analysis_functions.items():
            if _name == name:
                # Idiot check: Cannot register two implementations of same name for same subject type
                if (_subject_app_name, _subject_model) == (subject_app_name, subject_model):
                    raise AlreadyRegisteredAnalysisFunctionException(visualization_type, name, subject_app_name,
                                                                     subject_model)
                # Idiot check: Implementations of same name (but different subject type) should have identical default
                # arguments.
                _default_kwargs = _impl.default_kwargs
                if _default_kwargs != default_kwargs:
                    raise DefaultKwargsDifferException(name, subject_app_name, subject_model, default_kwargs,
                                                       _subject_app_name, _subject_model, _default_kwargs)

        # We are good: Actually register the implementation
        self._analysis_functions[key] = impl

    def get_implementation(self, name, subject_type):
        """
        Return AnalysisFunctionImplementation for given analysis function and subject type.

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
        subject_app_name = subject_type.app_label
        subject_model = subject_type.model
        try:
            return self._analysis_functions[(name, subject_app_name, subject_model)]
        except KeyError as exc:
            raise ImplementationMissingAnalysisFunctionException(name, subject_app_name, subject_model) from exc

    def get_analysis_function_names(self, user=None):
        """
        Returns function names as list.

        If given a user, only the functions are returned
        which have at least one implementation for the given user.
        """
        implementations = self._analysis_functions
        if user is not None:
            # filter for user
            implementations = { k:impl for k, impl in implementations.items()
                                if impl.is_available_for_user(user) }

        return list(set(name for name, subject_app_name, subject_model in implementations.keys()))

    def get_implementation_types(self, name):
        """Returns list of ContentType which can be given as first argument to function with given name."""
        return list(set(ContentType.objects.get_by_natural_key(subject_app_name, subject_model)
                        for n, subject_app_name, subject_model in self._analysis_functions.keys()
                        if n == name))

    def get_visualization_type_for_function_name(self, requested_name):
        """Return visualization type for given function name."""
        try:
            visualization_type = self._visualization_type_by_function_name[requested_name]
        except KeyError as exc:
            raise ValueError(f"No function registered with given name {requested_name}.") from exc
        try:
            visualization_app_name = self._app_name[visualization_type]
        except KeyError as exc:
            raise ValueError(f"No app name registered with visualization type {visualization_type}.") from exc
        return visualization_app_name, visualization_type

    def sync_analysis_functions(self, cleanup=False):
        """
        Make sure all analysis functions are represented in database.

        It's recommended to run this with cleanup=True if an analysis
        function should be removed.

        Parameters
        ----------

        cleanup: bool
            If True, delete all analysis functions for which no implementations exist
            and also delete all analyses related to those functions.
            Be careful, might delete existing analyses.
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
        _log.info(f"Syncing analysis functions with database - {len(function_names_used)} functions used - ..")

        for name in function_names_used:
            func, created = AnalysisFunction.objects.update_or_create(name=name)
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
    def add_download_function(self, visualization_type, spec, file_format, func):
        """Register implementation of a download function.

        You can use the @register_download_function decorator in order to
        add an implementation to the registry.

        Parameters
        ----------
        visualization_type: str
            visualization type
        spec: str
            Short name for what should be downloaded, e.g. 'results'
        file_format: str
            File format provided by the iven function
        func: function
            Python function which implements the download function
        """

        key = (visualization_type, spec, file_format)

        # Each implementation should only be defined once
        if key in self._download_functions:
            raise AlreadyRegisteredException(key)

        self._download_functions[key] = func

    def get_download_function(self, visualization_type, spec, file_format):
        """Return Python function for given parameters.

        Parameters
        ----------
        visualization_type: str
            visualization type
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
        key = (visualization_type, spec, file_format)

        try:
            return self._download_functions[key]
        except KeyError as exc:
            raise UnknownKeyException(key) from exc


######################################################################################
# Decorators for registering functions and classes (used from plugins)
######################################################################################
def register_implementation(visualization_app_name, visualization_type, name, subject_app_name="manager"):
    """
    Decorator for marking a function as implementation for an analysis function.

    Parameters
    ----------
    visualization_app_name: str
        App name that provides the analysis function, e.g. "analysis"
    visualization_type: str
        Visualization type, e.g. "series"
    name: str
        UI name of analysis function.
    subject_app_name: str
        App name where the subject is defined as model, e.g. "manager"
    """
    def register_decorator(func):
        """
        :param func: function to be registered, first arg must be a "topography" or "surface"
        :return: decorated function

        Depending on the name of the first argument, you get either a Topography
        or a Surface instance. The model is searched only for the given subject_app_name.
        """
        registry = AnalysisRegistry()  # singleton
        registry.add_implementation(visualization_app_name, visualization_type, name, subject_app_name, func)
        return func

    return register_decorator


def register_download_function(visualization_type, spec, file_format):
    """
    Decorator for marking a function as a download function.

    Parameters
    ----------
    visualization_type: str
        visualization type.
    spec: str
            Short name for what should be downloaded, e.g. 'results'
    file_format: str
        File format provided by the given function
    """
    def register_decorator(func):
        registry = AnalysisRegistry()  # singleton
        registry.add_download_function(visualization_type, spec, file_format, func)
        return func

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

    @property
    def python_function(self):
        """Return reference to corresponding Python function."""
        return self._pyfunc

    @property
    def signature(self):
        return inspect.signature(self._pyfunc)

    @staticmethod
    def _get_default_args(signature):
        # thanks to mgilson, his answer on SO:
        # https://stackoverflow.com/questions/12627118/get-a-function-arguments-default-value#12627202

        return {
            k: v.default
            for k, v in signature.parameters.items()
            if v.default is not inspect.Parameter.empty
        }

    @property
    def default_kwargs(self):
        """
        Return default keyword arguments as dict.

        Administrative arguments like
        'storage_prefix', 'progress_recorder' and 'dois'
        which are common to all functions, are excluded.
        """
        dkw = self._get_default_args(self.signature)
        if 'storage_prefix' in dkw:
            del dkw['storage_prefix']
        if 'progress_recorder' in dkw:
            del dkw['progress_recorder']
        if 'dois' in dkw:
            del dkw['dois']
        return dkw

    def eval(self, subject, **kwargs):
        """Evaluate implementation on given subject with given arguments."""
        return self.python_function(subject, **kwargs)

    def is_available_for_user(self, user):
        """Return whether this implementation is available for the given user."""

        app = _get_app_config_for_obj(self._pyfunc)

        if app is None:
            return False
        elif app.name == 'topobank.analysis':  # special case, should be always available
            return True

        from ..organizations.models import Organization
        plugins_available = Organization.objects.get_plugins_available(user)
        return app.name in plugins_available

    def get_subject_model(self):
        argspec = inspect.getfullargspec(self._pyfunc)
        return argspec.args[0]

def _get_app_config_for_obj(obj):
    """For given object, find out app config it belongs to."""
    from django.apps import apps

    search_path = obj.__module__
    if search_path.startswith('topobank.'):
        search_path = search_path[9:]  # otherwise app from topobank are not found
    app = None
    while app is None:
        try:
            app = apps.get_app_config(search_path)
        except LookupError:
            if ("." not in search_path) or app:
                break
            search_path, _ = search_path.rsplit(".", 1)
    # FIXME: `app` should not be None, except in certain tests. Can we add some form of guard here?
    #if app is None:
    #    raise RuntimeError(f'Could not find app config for {obj.__module__}. Is the Django app installed and '
    #                       f'registered? This is likely a misconfigured Django installation.')
    return app

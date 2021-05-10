"""
Registry for collection analysis functions.
"""
import inspect
import logging
from ..utils import Singleton

from django.contrib.contenttypes.models import ContentType

_log = logging.getLogger(__name__)


class AnalysisFunctionException(Exception):
    """Generic exception for problems while handling analysis functions."""
    pass


class UnknownAnalysisFunctionException(AnalysisFunctionException):
    """No Analysis function with given name known."""

    def __init__(self, name):
        self._name = name

    def __str__(self):
        return f"No analysis function defined with name '{self._name}'."


class NoImplementationException(AnalysisFunctionException):
    """No implementation for analysis function with given name registered."""

    def __init__(self, name):
        self._name = name

    def __str__(self):
        return f"No implementation has been registered for analysis function '{self._name}'."


class ImplementationAlreadyDefinedException(AnalysisFunctionException):
    """An implementation of an analysis function was already defined."""

    def __init__(self, name, subject_type_name):
        self._name = name
        self._subject_type_name = subject_type_name

    def __str__(self):
        return f"An implementation for analysis function '{self._name}' with subject type " +\
               f"'{self._subject_type_name}' was already defined."


class ImplementationMissingException(AnalysisFunctionException):
    """An analysis function implementation was not found for given subject type."""

    def __init__(self, name, subject_type):
        self._name = name
        self._subject_type = subject_type

    def __str__(self):
        return f"Implementation for analysis function '{self._name}' for subject type '{self._subject_type}' " +\
               " not found."


class InconsistentCardViewFlavorException(AnalysisFunctionException):
    """Card view flavor for an analysis function is not unique."""

    def __init__(self, name, curr_card_view_flavor, new_card_view_flavor):
        self._name = name
        self._curr_card_view_flavor = curr_card_view_flavor
        self._new_card_view_flavor = new_card_view_flavor

    def __str__(self):
        return f"An implementation for analysis function '{self._name}' was given with "+\
               f"card view flavor '{self._new_card_view_flavor}', but before "+\
               f"card view flavor '{self._curr_card_view_flavor}' was defined. It should be unique."


class UnknownCardViewFlavorException(AnalysisFunctionException):
    """Card view flavor for an analysis function is not known."""

    def __init__(self, name, card_view_flavor):
        self._name = name
        self._card_view_flavor = card_view_flavor

    def __str__(self):
        return f"An implementation for analysis function '{self._name}' was given with "+\
               f"card view flavor '{self._card_view_flavor}' which is unknown."


class AnalysisFunctionRegistry(metaclass=Singleton):
    """Central register for analysis functions.

    Collects function names, card view flavors and collections
    so these can be generated in database (see `sync` method).
    Checks consistency while collecting.
    """
    def __init__(self):
        self._implementations = {}
        # key: (name, subject_type_name)
        #      where name: Function name in UI,
        #      subject_type_name: "Topography" or "Surface" (type)
        # value: reference to implementation of analysis function

        self._card_view_flavors = {}
        # key: function name in UI
        # value: card view flavor

    def add_implementation(self, name, card_view_flavor, func):
        """Register implementation of an analysis function.

        Depending on the name of the first argument of the given function,
        this implementation is registered as a function being called for topographies
        or surfaces.

        You can use the @register_implementation decorator in order to
        add an implementation to the registry.

        Parameters
        ----------
        name: str
            Function name in the UI
        card_view_flavor: str
            Card view flavor, see AnalysisFunction model for possible values.
        func: function
            Python function which implements the analysis function
        """
        # Find out name of first argument
        func_spec = inspect.getfullargspec(func)
        subject_type_name = func_spec.args[0]
        # try:
        #     subject_type = ContentType.objects.get_by_natural_key('manager', first_arg_name)
        # except AttributeError as exc:
        #     err_msg = f'No model for name "{first_arg_name}" found. ' + \
        #             'Did you mean "topography" or "surface"?'
        #     raise ValueError(err_msg) from exc

        key = (name, subject_type_name)
        # We are using the subject_type_name here because otherwise we have problems
        # during test setup if we use Contenttypes here (not fully ready?)

        # Each implementation should only defined once
        if key in self._implementations:
            raise ImplementationAlreadyDefinedException(name, subject_type_name)

        # The card view flavor must be valid
        from topobank.analysis.models import CARD_VIEW_FLAVORS
        if card_view_flavor not in CARD_VIEW_FLAVORS:
            raise UnknownCardViewFlavorException(name, card_view_flavor)

        # For a given function name, the card view flavor should be unique
        if name in self._card_view_flavors:
            if card_view_flavor != self._card_view_flavors[name]:
                raise InconsistentCardViewFlavorException(name, card_view_flavor)

        self._implementations[key] = func
        self._card_view_flavors[name] = card_view_flavor

    def get_implementation(self, name, subject_type):
        """Return Python function for given analysis function and subject type.

        Parameters
        ----------
        name: str
            Name of analysis function.
        subject_type: ContentType
            ContentType of subject (first argument of implementing function)

        Returns
        -------
        Python function, first argument can accept given subject_type
        """
        try:
            return self._implementations[(name, subject_type.model)]
        except KeyError as exc:
            raise ImplementationMissingException(name, subject_type)

    def get_card_view_flavor(self, name):
        """Return card view flavor for analysis function with given name."""
        try:
            return self._card_view_flavors[name]
        except KeyError as exc:
            raise NoImplementationException(name) from exc

    def get_names(self):
        """Returns function names as list."""
        return self._card_view_flavors.keys()

    def sync(self, cleanup=False):
        """Make sure all implementations are represented in database.

        It's recommended to run this with cleanup=True if an analysis
        function should be removed.

        Parameters
        ----------

        cleanup: bool
            If True, delete all analysis functions for which no implementations exist
            and also delete all analyses related to those functions.
            Be careful, will delete existing analysis.
        """
        from .models import AnalysisFunction, AnalysisFunctionImplementation, Analysis

        counts = dict(
            funcs_updated=0,
            funcs_created=0,
            funcs_deleted=0,
            implementations_updated=0,
            implementations_created=0,
            implementations_deleted=0,
        )

        #
        # Ensure all analysis functions needed exist in database
        #
        function_names_used = []
        for name, card_view_flavor in self._card_view_flavors.items():
            func, created = AnalysisFunction.objects.update_or_create(defaults=dict(card_view_flavor=card_view_flavor),
                                                                      name=name)
            if created:
                counts['funcs_created'] += 1
            else:
                counts['funcs_updated'] += 1
            function_names_used.append(name)

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

        #
        # Ensure all implementations needed exist in database
        #
        for name, subject_type_name in self._implementations:
            function = AnalysisFunction.objects.get(name=name)
            subject_type = ContentType.objects.get_by_natural_key('manager', subject_type_name)
            pyfunc_obj = self._implementations[(name, subject_type_name)]
            pyfunc_name = pyfunc_obj.__name__
            impl, created = AnalysisFunctionImplementation.objects.update_or_create(
                defaults=dict(code_ref=pyfunc_name),
                function=function,
                subject_type=subject_type,
            )
            if created:
                counts['implementations_created'] += 1
            else:
                counts['implementations_updated'] += 1

        # If there is any implementation in the database which
        # has no representative in the code, delete it:
        for impl in AnalysisFunctionImplementation.objects.all():
            key = (impl.function.name, impl.subject_type.name)
            if key not in self._implementations:
                impl.delete()
                counts['implementations_deleted'] += 1

        return counts


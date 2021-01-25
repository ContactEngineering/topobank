"""
Registry for collection analysis functions.
"""
import inspect
from ..utils import Singleton

from django.contrib.contenttypes.models import ContentType


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

    def __init__(self, name, subject_type):
        self._name = name
        self._subject_type = subject_type

    def __str__(self):
        return f"An implementation for analysis function '{self._name}' with first argument " +\
               f"'{self._subject_type}' was already defined."


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
        # key: (name, subject_type)
        #      where name: Function name in GUI, subject_type: Topography or Surface (type)
        # value: reference to implementation of analysis function

        self._card_view_flavors = {}
        # key: name
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
            Function name in the GUI
        card_view_flavor: str
            Card view flavor, see AnalysisFunction model for possible values.
        func: function
            Python function which implements the analysis function
        """
        # Find out name of first argument
        func_spec = inspect.getfullargspec(func)
        first_arg_name = func_spec.args[0]
        try:
            subject_type = ContentType.objects.get_by_natural_key('manager', first_arg_name)
        except AttributeError as exc:
            err_msg = f'No model for name "{first_arg_name}" found. ' + \
                    'Did you mean "topography" or "surface"?'
            raise ValueError(err_msg) from exc

        key = (name, subject_type)

        # Each implementation should only defined once
        if key in self._implementations:
            raise ImplementationAlreadyDefinedException(name, subject_type)

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
        """Return Python function for given analysis function and first argument type.

        Parameters
        ----------
        name: str
            Name of analysis function.
        subject_type: type
            Either Topography or Surface

        Returns
        -------
        Python function, first argument must be of type `subject_type`.
        """
        try:
            return self._implementations[(name, subject_type)]
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

    def sync(self):
        """Make sure all implementations are represented in database.
        """
        from .models import AnalysisFunction, AnalysisFunctionImplementation

        counts = dict(
            funcs_updated=0,
            funcs_created=0,
            implementations_updated=0,
            implementations_created=0,
        )

        for name, card_view_flavor in self._card_view_flavors.items():
            func, created = AnalysisFunction.objects.update_or_create(defaults=dict(card_view_flavor=card_view_flavor),
                                                                      name=name)
            if created:
                counts['funcs_created'] += 1
            else:
                counts['funcs_updated'] += 1

        for name, subject_type in self._implementations:
            function = AnalysisFunction.objects.get(name=name)
            pyfunc_obj = self._implementations[(name, subject_type)]
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

        return counts


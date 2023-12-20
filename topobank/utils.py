"""
Some helper functions
"""

import datetime
import io
import json

from django.core.files.storage import default_storage
from django.utils import formats
from django.test import SimpleTestCase

from .manager.utils import default_storage_replace
from .supplib.json import ExtendedJSONEncoder

DEFAULT_DEBUG_HTML_FILENAME = '/tmp/response.html'
JSON_CONSTANTS = {
    'NaN': float("nan"),
    '-Infinity': float("-inf"),
    'Infinity': float("inf")
}


def export_reponse_as_html(response, fname=DEFAULT_DEBUG_HTML_FILENAME):
    """
    Helper function which can be used for debugging.

    :param response: HTTPResponse
    :param fname: name of HTML output file
    """
    f = open(fname, mode='w')

    f.write(response.content.decode('utf-8').replace('\\n', '\n'))
    f.close()


def assert_in_content(response, x):
    """Check whether x is in the content of given response"""

    if isinstance(x, bytes):
        in_content = x in response.content
    else:
        if isinstance(x, datetime.date):
            x = formats.date_format(x)
        else:
            x = str(x)
        in_content = bytes(x, encoding='utf-8') in response.content

    if not in_content:
        export_reponse_as_html(response)  # for debugging

    assert in_content, f"Cannot find '{x}' in this content:\n{response.content}.\n\n" + \
                       f"See file://{DEFAULT_DEBUG_HTML_FILENAME} in order to view the output."


def assert_not_in_content(response, x):
    """Check whether x is NOT in the content of given response"""

    if isinstance(x, datetime.date):
        representation = formats.date_format(x)
    else:
        representation = str(x)

    in_content = bytes(representation, encoding='utf-8') in response.content

    if in_content:
        export_reponse_as_html(response)  # for debugging

    assert not in_content, f"Unexpectedly, there is '{representation}' in this content:\n{response.content}.\n\n" + \
                           f"See file://{DEFAULT_DEBUG_HTML_FILENAME} in order to view the output."


def assert_no_form_errors(response):
    """Asserts that there is no more form, and if there is, show errors in form"""
    assert ('form' not in response.context) or (len(response.context['form'].errors) == 0), \
        "Form is still in context, with errors: {}".format(response.context['form'].errors)


def assert_form_error(response, error_msg_fragment, field_name=None):
    """Asserts that there is an error in form.

    Parameters
    ----------
    response: HTTPResponse object
    error_msg_fragment: str
        Substring which should be included in the error message.
    field_name: str, optional
        Name of field for which the error is expected to occur.
        If a general error message (not bound to a field) is meant,
        use `None`.

    Returns
    -------
    None

    Raises
    ------
    AssertionError
        If forms hasn't errors or not for the field as expected or the substring was not included.
    """
    assert ('form' in response.context) and (len(response.context['form'].errors) > 0), \
        "Form is expected to show errors, but there is no error."

    if not field_name:
        field_name = '__all__'

    assert field_name in response.context['form'].errors, \
        "Form shows errors, but not {} which is expected. Errors: {}".format(
            "independent from a special field" if field_name == '__all__' else f"for field '{field_name}'",
            response.context['form'].errors
        )

    errors = response.context['form'].errors[field_name]

    assert any((error_msg_fragment in err) for err in errors), \
        (f"Form has errors as expected, but no error contains the given error message fragment "
         f"'{error_msg_fragment}'. Instead: {errors}")


# abbreviation for use with pytest
assert_redirects = SimpleTestCase().assertRedirects


class Singleton(type):
    """Ensure that there is only one instance per class.

    Usage:

    class Logger(metaclass=Singleton):
        pass
    """
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class SplitDictionaryHere:
    """Wrapper class for usage with `store_split_dict`.

    This allows to wrap a dictionary such that the function
    `store_split_dict` stores it in a separate file in storage.
    See there for more information.
    """

    def __init__(self, name, dict, supplementary={}):
        """

        Parameters
        ----------
        name : str
            Name of the subdirectionary. This will be used as a file prefix
            when writing this dictionary to JSON
        dict : dict
            The actual dictionary.
        supplementary : dict
            Supplementary dictionary to include only into the split variant.
        """
        self._name = name
        self._dict = dict
        self._supplementary = supplementary

    def __getitem__(self, key):
        return self._dict.__getitem__(key)

    def __setitem__(self, key, value):
        return self._dict.__setitem__(key, value)

    @property
    def name(self):
        return self._name

    @property
    def dict(self):
        return self._dict

    @property
    def supplementary(self):
        return self._supplementary


def store_split_dict(storage_prefix, name, src_dict):
    """Store a dictionary in storage with optional splitting into several files.

    Parameters
    ----------
    storage_prefix: str
        prefix in storage
    name: str
        determines the files name under which the dict is stored, the extension '.json' is appended automatically.
    src_dict: dict
        dictionary to store, if it contains elements which are instances of `SplitDictionaryHere`,
        the corresponding dictionary is saved into a separate file, not in the root file which
        represents `src_dict`.

    Returns
    -------
    None

    The stored data can be retrieved again from multiple files by using `load_split_dict`,
    given the `storage prefix` and `name` used here to store the dict.

    Caution: Don't use the string literals "NaN" and "Infinity" and "-Infinity" as
             values, unless you want them decoded as the corresponding float values.
             This is a workaround for not having NaN in the JSON standard.
    """
    # Traverse dictionary and search for instances of SplitDictionaryHere.
    # Those are written to separate files.

    # We're using our own JSON encoder here, because it represents NaN values as "NaN" (with quotes),
    # which is JSON compatible (only works with Numpy arrays)
    encoder_cls = ExtendedJSONEncoder

    def _split_dict(d):
        if isinstance(d, SplitDictionaryHere):
            split_d = _split_dict(d.dict)
            default_storage_replace(f'{storage_prefix}/{d.name}.json',
                                    io.BytesIO(json.dumps(split_d, cls=encoder_cls).encode('utf-8')))
            # Include supplementary dictionary in the toplevel JSON
            return {**{'__external__': f'{d.name}.json'}, **d.supplementary}
        elif hasattr(d, 'items'):
            new_d = {}
            for key, value in d.items():
                new_d[key] = _split_dict(value)
            return new_d
        elif isinstance(d, list):
            new_d = []
            for value in d:
                new_d.append(_split_dict(value))
            return new_d
        else:
            return d

    split_d = _split_dict(src_dict)
    default_storage_replace(f'{storage_prefix}/{name}.json',
                            io.BytesIO(json.dumps(split_d, cls=encoder_cls).encode('utf-8')))


def load_split_dict(storage_prefix, name):
    """Load split dicts from storage, previously written by `store_split_dict`.

    Parameters
    ----------
    storage_prefix: str
        Storage prefix used as parameter of `store_split_dict`.
    name: str
        Name used as parameter of `store_split_dict`.

    Returns
    -------
    Original dict as stored with `store_split_dict`, but without the wrapper classes
    of type `SplitDictionaryHere`.
    """

    def _unsplit_dict(d):
        if hasattr(d, 'items'):
            new_d = {}
            for key, value in d.items():
                if key == '__external__':
                    # '__external__' will override anything that is at this level in the dictionary
                    return _unsplit_dict(json.load(default_storage.open(f'{storage_prefix}/{value}')))
                new_d[key] = _unsplit_dict(value)
            return new_d
        elif isinstance(d, list):
            new_d = []
            for value in d:
                new_d.append(_unsplit_dict(value))
            return new_d
        elif isinstance(d, str) and (d in JSON_CONSTANTS):
            # reinsert NaN instead of "NaN" (with quotes)
            return JSON_CONSTANTS[d]
        else:
            return d

    d = json.load(default_storage.open(f'{storage_prefix}/{name}.json'))
    return _unsplit_dict(d)

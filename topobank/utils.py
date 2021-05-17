#
# Some helpers useful during testing
#
import datetime
from django.utils import formats
from django.test import SimpleTestCase

DEFAULT_DEBUG_HTML_FILENAME = '/tmp/response.html'


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

    if isinstance(x, datetime.date):
        representation = formats.date_format(x)
    else:
        representation = str(x)

    in_content = bytes(representation, encoding='utf-8') in response.content

    if not in_content:
        export_reponse_as_html(response)  # for debugging

    assert in_content, f"Cannot find '{representation}' in this content:\n{response.content}.\n\n" + \
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
        Field name for which the error should occur.
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
        f"Form has errors as expected, but no error contains the given error message fragment '{error_msg_fragment}'." + \
        f" Instead: {errors}"


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

import re

from django.forms import forms
from django import forms
from django.conf import settings
import bleach  # using bleach instead of django.utils.html.escape because it allows more (e.g. for markdown)

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field, HTML, Div, Fieldset
from crispy_forms.bootstrap import FormActions

try:
    from bootstrap_datepicker_plus.widgets import DatePickerInput
except ModuleNotFoundError:
    from bootstrap_datepicker_plus import DatePickerInput

import logging

from .models import Surface

_log = logging.getLogger(__name__)

ASTERISK_HELP_HTML = HTML("<p>Fields marked with an asterisk (*) are mandatory.</p>")
DEFAULT_LICENSE = 'ccbysa-4.0'


class SurfacePublishForm(forms.Form):
    """Form for publishing surfaces."""
    license = forms.ChoiceField(widget=forms.RadioSelect, choices=Surface.LICENSE_CHOICES,
                                required=True)
    agreed = forms.BooleanField(widget=forms.CheckboxInput, required=True,
                                label="I understand the implications of publishing this surface and I agree.",
                                help_text="""Please read the implications of publishing listed above and check.""")
    copyright_hold = forms.BooleanField(widget=forms.CheckboxInput, required=True,
                                        label="I hold copyright of this data or have been authorized by the copyright holders.",
                                        help_text="""Please make sure you're not publishing data """
                                                  """from others without their authorization.""")

    authors_json = forms.JSONField(required=True)

    helper = FormHelper()
    helper.form_method = 'POST'
    error_text_inline = False
    helper.attrs = {"onsubmit": "on_submit()"}  # call JS function for disabling button
    # this prevents multiple submissions by clicking several times fast

    helper.layout = Layout(
        Div(
            HTML('<h2 class="alert-heading">Please enter the authors</h2>'),
            Field('authors_json', template="manager/multi_author_field.html"),
            css_class="alert alert-primary"
        ),
        Div(
            HTML('<h2 class="alert-heading">Please choose a license</h2>'),
            Field('license', template="manager/license_radioselect.html"),
            css_class="alert alert-primary"
        ),
        Div(
            HTML('<h2 class="alert-heading">Final checks</h2>'),
            Field('agreed'),
            Field('copyright_hold'),
            FormActions(
                Submit('save', 'Yes, publish this surface', css_class='btn-success'),
                HTML("""
                      <a href="{% url 'manager:surface-detail' surface.pk %}" class="btn btn-default" id="cancel-btn">Cancel</a>
                      """),
            ),
            ASTERISK_HELP_HTML,
            css_class="alert alert-primary"),
    )

    def clean(self):
        cleaned_data = super().clean()

        #
        # Check each author
        #
        # - Check that only valid fields are included
        # - bleach all fields in order to prevent XSS attacks
        # - strip text fields
        # - first and last name given?
        # - if ORCID given, correct format?
        # - if affiliation given, is there a name? If no data given, remove.
        # - if affiliation ROR ID given, correct format?
        # - has this author already given with same data?

        authors = self.cleaned_data.get('authors_json')

        if (authors is None) or (len(authors) == 0):
            raise forms.ValidationError("At least one author must be given.")

        if len(authors) > settings.PUBLICATION_MAX_NUM_AUTHORS:
            raise forms.ValidationError(f"Too many authors given, at maximum {settings.PUBLICATION_MAX_NUM_AUTHORS}"
                                        "allowed.")
        try:
            for a in authors:
                for k in a.keys():
                    if k not in ['first_name', 'last_name', 'orcid_id', 'affiliations']:
                        raise forms.ValidationError(f"Invalid key {k} given in author definition.")
                for k in ['first_name', 'last_name', 'orcid_id']:
                    a[k] = bleach.clean(a[k].strip())
                if a['first_name'] == '':
                    raise forms.ValidationError("First name must be given for each author.")
                if a['last_name'] == '':
                    raise forms.ValidationError("Last name must be given for each author.")
                if a['orcid_id'] != '' and not re.match('^\d{4}-\d{4}-\d{4}-\d{3}[0-9X]$', a['orcid_id']):
                    raise forms.ValidationError("ORCID ID must match pattern xxxx-xxxx-xxxx-xxxy, where x is a digit "
                                                "and y a digit or the capital letter X.")

                if len(a['affiliations']) > settings.PUBLICATION_MAX_NUM_AFFILIATIONS_PER_AUTHOR:
                    raise forms.ValidationError(
                        f"Too many affiliations given, at maximum {settings.PUBLICATION_MAX_NUM_AFFILIATIONS_PER_AUTHOR}"
                        "allowed per author.")

                new_affs = []
                for aff in a['affiliations']:
                    try:
                        aff['name'] = bleach.clean(aff['name'].strip())
                        name_given = len(aff['name']) > 0
                    except KeyError:
                        name_given = False
                    try:
                        aff['ror_id'] = bleach.clean(aff['ror_id'].strip())
                        ror_id_given = len(aff['ror_id']) > 0
                    except KeyError:
                        ror_id_given = False

                    if name_given:
                        if ror_id_given and not re.match('^0[^ilouILOU]{6}\d{2}$', aff['ror_id']):
                            raise forms.ValidationError(
                                f"Incorrect format for ROR ID \'{aff['ror_id']}\', should start with 0 (zero), followed "
                                "by 6 characters and should end with 2 digits."
                            )
                        new_affs.append(aff)  # only this one should be used, empty affiliations will be ignored
                    else:
                        if ror_id_given:
                            raise forms.ValidationError(
                                f"Please specify a name for affiliation with ROR ID {aff['ror_id']}."
                            )
                a['affiliations'] = new_affs

            #
            # Brute force search for duplicates
            #
            for a_idx, a in enumerate(authors):
                for b in authors[a_idx + 1:]:
                    if a == b:
                        raise forms.ValidationError("Duplicate author given! Make sure authors differ "
                                                    "in at least one field.")
        except forms.ValidationError:
            raise
        except Exception as exc:
            msg = f"Problems while parsing authors' data: {exc}"
            _log.error(msg)
            raise forms.ValidationError("Problems while parsing authors' data.")  # we provide no more detail here

        cleaned_data['authors_json'] = authors

        return cleaned_data

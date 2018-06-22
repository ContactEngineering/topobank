from django import forms
from django.conf import settings
import logging
import re

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field, Button, HTML, Div, Hidden, Fieldset
from crispy_forms.bootstrap import (InlineCheckboxes, TabHolder, Tab,
    PrependedText, PrependedAppendedText, FormActions, InlineRadios)

from .models import Topography

_log = logging.getLogger('manager')

################################################################
# Topography Forms
################################################################
class TopographyForm(forms.ModelForm):
    """Form for creating or updating topographies-
    """

    def __init__(self, *args, **kwargs):
        super(TopographyForm, self).__init__(*args, **kwargs)
        self.fields['user'].label = False

    class Meta:
        model = Topography
        fields = ('description', 'measurement_date', 'datafile', 'user')

    helper = FormHelper()
    helper.form_method = 'POST'
    helper.form_show_errors = False  # crispy forms has nicer template code for errors

    datafile = forms.FileInput()
    measurement_date = forms.DateField(input_formats=['%Y-%m-%d', '%d.%m.%Y'])
    description = forms.Textarea()

    helper.layout = Layout(
        Div(
            Field('datafile'),
            Field('measurement_date'),
            Field('description'),
            Field('user', type="hidden"), # TODO check whether data could be manipulated in client
        ),
        FormActions(
                Submit('save', 'Save'),
                HTML("""
                    <a href="{% url 'manager:list' %}" class="btn btn-default" id="cancel-btn">Cancel</a>
                """),
            ),
    )


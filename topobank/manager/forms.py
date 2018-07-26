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

class TopographyFileUploadForm(forms.ModelForm):

    class Meta:
        model = Topography
        fields = ('datafile',)

    helper = FormHelper()
    helper.form_method = 'POST'
    helper.form_show_errors = False  # crispy forms has nicer template code for errors
    helper.form_tag = False # we use an own form tag with the wizard

    datafile = forms.FileField()

    helper.layout = Layout(
        Div(
            Field('datafile'),
        ),
        FormActions(
            Submit('save', 'Next'),
            HTML("""
                <a href="{% url 'manager:list' %}"><button class="btn btn-default" id="cancel-btn">Cancel</button></a>
            """),
        ),
    )

class TopographyMetaDataForm(forms.ModelForm):

    class Meta:
        model = Topography
        fields = ('name', 'description', 'measurement_date', 'data_source', 'datafile', 'user')

    def __init__(self, *args, **kwargs):
        data_source_choices = kwargs.pop('data_source_choices')
        super(TopographyMetaDataForm, self).__init__(*args, **kwargs)
        self.fields['data_source'] = forms.ChoiceField(choices=data_source_choices)


    helper = FormHelper()
    helper.form_method = 'POST'
    helper.form_show_errors = False  # crispy forms has nicer template code for errors
    helper.form_tag = False

    name = forms.CharField()
    measurement_date = forms.DateField(input_formats=['%Y-%m-%d', '%d.%m.%Y'])
    description = forms.Textarea()

    # physical_size =
    # height conversion factor
    # detrending

    helper.layout = Layout(
        Div(
            Field('datafile', type="hidden"),
            Field('user', type="hidden"),
            Field('data_source'),
            Field('name'),
            Field('measurement_date'),
            Field('description'),
            # TODO add other meta data fields
        ),
        FormActions(
            #HTML("""
            #    {% if wizard.steps.prev %}
            #        <button name="wizard_goto_step" class="btn btn-default" type="submit" value="{{ wizard.steps.prev }}">Previous</button>
            #    {% endif %}
            #    """), # Add this if user should be able to go back - but currently form is also validated before
            Submit('save', 'Save new topography'),
            HTML("""
                    <a href="{% url 'manager:list' %}"><button class="btn btn-default" id="cancel-btn">Cancel</button></a>
            """),
        ),
    )

    def clean(self):
        return self.cleaned_data

class TopographyForm(forms.ModelForm):
    """Form for creating or updating topographies-
    """

    def __init__(self, *args, **kwargs):
        #data_source_choices = kwargs.pop('data_source_choices')
        super(TopographyForm, self).__init__(*args, **kwargs)
        self.fields['user'].label = False
        #self.fields['data_source'] = forms.ChoiceField(choices=data_source_choices)

    class Meta:
        model = Topography
        fields = ('name', 'description', 'measurement_date', 'datafile', 'user')

    helper = FormHelper()
    helper.form_method = 'POST'
    helper.form_show_errors = False  # crispy forms has nicer template code for errors

    datafile = forms.FileInput()
    measurement_date = forms.DateField(input_formats=['%Y-%m-%d', '%d.%m.%Y'])
    description = forms.Textarea()

    helper.layout = Layout(
        Div(
            Field('datafile', readonly=True),
            Field('data_source', readonly=True),
            Field('name'),
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


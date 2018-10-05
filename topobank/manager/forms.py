from django.forms import forms, TypedMultipleChoiceField
from django import forms
from django_select2.forms import Select2MultipleWidget
import logging

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field, HTML, Div, Fieldset
from crispy_forms.bootstrap import FormActions

from topobank.manager.utils import selection_choices
from .models import Topography, Surface

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
                <a href="{% url 'manager:surface-list' %}"><button class="btn btn-default" id="cancel-btn">Cancel</button></a>
            """),
        ),
    )

class TopographyMetaDataForm(forms.ModelForm):

    class Meta:
        model = Topography
        fields = ('name', 'description', 'measurement_date',
                  'data_source', 'datafile', 'surface',
                  )

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

    helper.layout = Layout(
        Div(
            Field('surface', type="hidden"),
            Field('datafile', type="hidden"),
            Field('data_source'),
            Field('name'),
            Field('measurement_date'),
            Field('description'),
        ),
        FormActions(
            #HTML("""
            #    {% if wizard.steps.prev %}
            #        <button name="wizard_goto_step" class="btn btn-default" type="submit" value="{{ wizard.steps.prev }}">Previous</button>
            #    {% endif %}
            #    """), # Add this if user should be able to go back - but currently form is also validated before
            Submit('save', 'Next'),
            HTML("""
                    <a href="{% url 'manager:surface-list' %}"><button class="btn btn-default" id="cancel-btn">Cancel</button></a>
            """), # TODO check back link
        ),
    )

    def clean(self):
        return self.cleaned_data

class TopographyUnitsForm(forms.ModelForm):

    class Meta:
        model = Topography
        fields = ( 'datafile', 'surface',
                   'name', 'description', 'measurement_date',
                   'data_source',
                   'size_x', 'size_y', 'size_unit',
                   'height_scale', 'height_unit', 'detrend_mode')



    helper = FormHelper()
    helper.form_method = 'POST'
    helper.form_show_errors = False  # crispy forms has nicer template code for errors
    helper.form_tag = False

    name = forms.CharField()
    measurement_date = forms.DateField(input_formats=['%Y-%m-%d', '%d.%m.%Y'])
    description = forms.Textarea()

    helper.layout = Layout(
        Div(
            Field('surface', type="hidden"),
            Field('datafile', type="hidden"),
            Field('measurement_date', type="hidden"),
            Field('data_source', type="hidden"),
            Field('name', type="hidden"),
            Fieldset('Physical Size', 'size_x', 'size_y', 'size_unit'),
            Fieldset('Height Conversion', 'height_scale', 'height_unit'),
            Field('detrend_mode'),
        ),
        FormActions(
            #HTML("""
            #    {% if wizard.steps.prev %}
            #        <button name="wizard_goto_step" class="btn btn-default" type="submit" value="{{ wizard.steps.prev }}">Previous</button>
            #    {% endif %}
            #    """), # Add this if user should be able to go back - but currently form is also validated before
            Submit('save', 'Save new topography'),
            HTML("""
                    <a href="{% url 'manager:surface-list' %}"><button class="btn btn-default" id="cancel-btn">Cancel</button></a>
            """),
        ),
    )

    def clean(self):
        return self.cleaned_data


class TopographyForm(forms.ModelForm):
    """Form for creating or updating topographies-
    """

    class Meta:
        model = Topography
        fields = ('name', 'description', 'measurement_date',
                  'datafile', 'data_source',
                  'size_x', 'size_y', 'size_unit',
                  'height_scale', 'height_unit', 'detrend_mode',
                  'surface')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for fn in ['surface', 'data_source']:
            self.fields[fn].label = False


    helper = FormHelper()
    helper.form_method = 'POST'
    helper.form_show_errors = False  # crispy forms has nicer template code for errors

    datafile = forms.FileInput()
    measurement_date = forms.DateField(input_formats=['%Y-%m-%d', '%d.%m.%Y'])
    description = forms.Textarea()

    helper.layout = Layout(
        Div(
            #Field('datafile', readonly=True, hidden=True),
            Field('surface', readonly=True, hidden=True),
            Field('data_source', readonly=True, hidden=True),
            Field('name'),
            Field('measurement_date'),
            Field('description'),
            Fieldset('Physical Size', 'size_x', 'size_y', 'size_unit'),
            Fieldset('Height Conversion', 'height_scale', 'height_unit'),
            Field('detrend_mode'),
        ),
        FormActions(
                Submit('save', 'Save'),
                HTML("""
                    <a href="{% url 'manager:topography-detail' object.id %}" class="btn btn-default" id="cancel-btn">Cancel</a>
                """),# TODO check back point
            ),
    )

class SurfaceForm(forms.ModelForm):
    """Form for creating or updating surfaces.
    """

    class Meta:
        model = Surface
        fields = ('name', 'user')

    helper = FormHelper()
    helper.form_method = 'POST'
    helper.form_show_errors = False  # crispy forms has nicer template code for errors

    helper.layout = Layout(
        Div(
            Field('name'),
            Field('user', type="hidden"),
        ),
        FormActions(
                Submit('save', 'Save'),
                HTML("""
                    <a href="{% url 'manager:surface-list' %}" class="btn btn-default" id="cancel-btn">Cancel</a>
                """),# TODO check back point for cancel
            ),
    )


class TopographySelectForm(forms.Form):

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

        self.fields['selection'].choices = lambda : selection_choices(user)

    selection = TypedMultipleChoiceField(
        required=False,
        widget=Select2MultipleWidget,
        label="Selected Topographies or Surfaces",
        help_text="Select one or multiple topographies or surfaces. Search by name.")

    helper = FormHelper()
    helper.form_method = 'POST'

    helper.layout = Layout(
        Field('selection'),

        FormActions(
            Submit('save', 'Save selection', css_class='btn-primary'),
            Submit('select-all', 'Select all', css_class='btn-primary'),
            Submit('analyze', 'Trigger analysis for selection', css_class='btn-primary'),
        ),
    )

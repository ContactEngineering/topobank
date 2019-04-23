from django.forms import forms, TypedMultipleChoiceField
from django import forms
from django_select2.forms import Select2MultipleWidget

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field, HTML, Div, Fieldset
from crispy_forms.bootstrap import FormActions

import logging

from topobank.manager.utils import selection_choices, \
    TopographyFile, TopographyFileReadingException, TopographyFileFormatException
from .models import Topography, Surface

_log = logging.getLogger(__name__)

MEASUREMENT_DATE_INPUT_FORMATS = ['%Y-%m-%d', '%d.%m.%Y']
MEASUREMENT_DATE_HELP_TEXT = 'Valid formats: "YYYY-mm-dd" or "dd.mm.YYYY"'

################################################################
# Topography Forms
################################################################

class TopographyFileUploadForm(forms.ModelForm):

    class Meta:
        model = Topography
        fields = ('datafile', 'surface')

    helper = FormHelper()
    helper.form_method = 'POST'
    helper.form_show_errors = False  # crispy forms has nicer template code for errors
    helper.form_tag = False # we use an own form tag with the wizard

    datafile = forms.FileField()

    helper.layout = Layout(
        Div(
            Field('datafile'),
            Field('surface', type='hidden') # in order to have data later in wizard's done() method
        ),
        FormActions(
            Submit('save', 'Next'),
            Submit('cancel', 'Cancel', formnovalidate="formnovalidate"),
        ),
    )

    def clean_datafile(self):
        # try to load topography file, show up error if this doesn't work
        datafile = self.cleaned_data['datafile']
        try:
            tf = TopographyFile(datafile.file) # TODO can be avoid to load the file more than once and still have a check?
        except TopographyFileReadingException as exc:
            msg = f"Error while reading file contents of file '{datafile.name}', detected format: {exc.detected_format}. "
            if exc.message:
                msg += f"Reason: {exc.message} "

            msg += " Please try another file or contact us."
            _log.info(msg+" Exception: "+str(exc))
            raise forms.ValidationError(msg, code='invalid_topography_file')
        except TopographyFileFormatException as exc:
            msg = f"Cannot determine file format of file '{datafile.name}'. "
            msg += "Please try another file or contact us."
            raise forms.ValidationError(msg, code='invalid_topography_file')

        if len(tf.data_sources) == 0:
            raise forms.ValidationError("No topographies found in file.", code='empty_topography_file')

        first_topo = tf.topography(0)
        if first_topo.dim > 2:
            raise forms.ValidationError("Number of surface map dimensions > 2.", code='invalid_topography')

        return self.cleaned_data['datafile']


class TopographyMetaDataForm(forms.ModelForm):

    class Meta:
        model = Topography
        fields = ('name', 'description', 'measurement_date', 'data_source')

    def __init__(self, *args, **kwargs):
        data_source_choices = kwargs.pop('data_source_choices')
        super(TopographyMetaDataForm, self).__init__(*args, **kwargs)
        self.fields['data_source'] = forms.ChoiceField(choices=data_source_choices)


    helper = FormHelper()
    helper.form_method = 'POST'
    helper.form_show_errors = False  # crispy forms has nicer template code for errors
    helper.form_tag = False

    name = forms.CharField()
    measurement_date = forms.DateField(input_formats=MEASUREMENT_DATE_INPUT_FORMATS,
                                       help_text=MEASUREMENT_DATE_HELP_TEXT)
    description = forms.Textarea()

    helper.layout = Layout(
        Div(
            Field('data_source'),
            Field('name'),
            Field('measurement_date'),
            Field('description'),
        ),
        FormActions(
            Submit('save', 'Next'),
            Submit('cancel', 'Cancel', formnovalidate="formnovalidate"),
        ),
    )

    def clean(self):
        return self.cleaned_data


class TopographyUnitsForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        helper = FormHelper()
        helper.form_method = 'POST'
        helper.form_show_errors = False  # crispy forms has nicer template code for errors
        helper.form_tag = False

        self.helper = helper

        if self.initial['size_editable']:
            self.size_info_html = HTML("<p>Please check this physical size and change it, if needed.</p>")
            self.size_field_kwargs = {}
        else:
            self.size_info_html = HTML("<p>Physical size was given in data file and is fixed.</p>")
            self.size_field_kwargs = dict(readonly=True)  # will add "readonly" attribute to input field

        if self.initial['unit_editable']:
            self.unit_info_html = HTML(
                "<p>Please select the correct unit for the size and height values.</p>")
            self.unit_field_kwargs = dict()
        else:
            self.unit_info_html = HTML(
                "<p>The unit of the physical size and height scale was given in the data file " + \
                "and is fixed.</p>")
            self.unit_field_kwargs = dict(type="hidden")
            # "readonly" attribute does not work for dropdowns here

        if self.initial['height_scale_editable']:
            self.height_scale_info_html = HTML(
                "<p>Please enter the correct height scale factor.</p>")
            self.height_scale_field_kwargs = {}
        else:
            self.height_scale_info_html = HTML(
                "<p>The height scale factor was given in the data file and is fixed.</p>")
            self.height_scale_field_kwargs = dict(readonly=True)

        # we want the "_editable" fields to be saved also with their current values, so we
        # prepare hidden fields for them
        self.editable_fields = [
            Field('size_editable', type='hidden'),
            Field('unit_editable', type='hidden'),
            Field('height_scale_editable', type='hidden'),
        ]

    def _clean_size_element(self, dim_name):
        """Checks whether given value is larger than zero.

        :param dim_name: "x" or "y"
        :return: cleaned size element value
        """

        size_elem_name = 'size_' + dim_name

        size_elem = self.cleaned_data[size_elem_name]

        if size_elem <= 0:
            msg = "Size {} must be greater than zero.".format(dim_name)
            raise forms.ValidationError(msg, code='size_element_zero_or_negative')

        return size_elem

    def clean_size_x(self):
        return self._clean_size_element('x')

class Topography1DUnitsForm(TopographyUnitsForm):

    class Meta:
        model = Topography
        fields = ('size_editable',
                  'unit_editable',
                  'height_scale_editable',
                  'size_x', 'unit',
                  'height_scale', 'detrend_mode',
                  'resolution_x') # resolution_y, size_y is saved as NULL

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper.layout = Layout(
            Div(
                Fieldset('Physical Size',
                         Field('size_editable', type="hidden"),
                         self.size_info_html,
                         Field('size_x', **self.size_field_kwargs),
                         self.unit_info_html,
                         Field('unit', **self.unit_field_kwargs)),
                Fieldset('Height Conversion',
                         self.height_scale_info_html,
                         Field('height_scale', **self.height_scale_field_kwargs)),
                Field('detrend_mode'),
                Field('resolution_x', type="hidden"),  # only in order to have the data in wizard's .done() method
                *self.editable_fields,
            ),
            FormActions(
                Submit('save', 'Save new topography'),
                Submit('cancel', 'Cancel', formnovalidate="formnovalidate"),
            ),
        )

class Topography2DUnitsForm(TopographyUnitsForm):

    class Meta:
        model = Topography
        fields = ('size_editable',
                  'unit_editable',
                  'height_scale_editable',
                  'size_x', 'size_y', 'unit',
                  'height_scale', 'detrend_mode',
                  'resolution_x', 'resolution_y')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper.layout = Layout(

            Div(
                Fieldset('Physical Size',
                         self.size_info_html,
                         Field('size_x', **self.size_field_kwargs),
                         Field('size_y', **self.size_field_kwargs),
                         self.unit_info_html,
                         Field('unit', **self.unit_field_kwargs)),
                Fieldset('Height Conversion',
                         self.height_scale_info_html,
                         Field('height_scale', **self.height_scale_field_kwargs)),
                Field('detrend_mode'),
                Field('resolution_x', type="hidden"), # only in order to have the data in wizard's .done() method
                Field('resolution_y', type="hidden"), # only in order to have the data in wizard's .done() method
                *self.editable_fields,
            ),
            FormActions(
                Submit('save', 'Save new topography'),
                Submit('cancel', 'Cancel', formnovalidate="formnovalidate"),
            ),
        )

    def clean_size_y(self):
        return self._clean_size_element('y')


class TopographyForm(TopographyUnitsForm):
    """Form for updating topographies.
    """

    class Meta:
        model = Topography
        fields = ('size_editable',
                  'unit_editable',
                  'height_scale_editable',
                  'name', 'description', 'measurement_date',
                  'datafile', 'data_source',
                  'size_x', 'size_y', 'unit',
                  'height_scale', 'detrend_mode',
                  'surface')

    def __init__(self, *args, **kwargs):
        has_size_y = kwargs.pop('has_size_y')
        super().__init__(*args, **kwargs)

        for fn in ['surface', 'data_source']:
            self.fields[fn].label = False

        self.helper.form_tag = True

        size_fieldset_args = ['Physical Size',
                               self.size_info_html,
                               Field('size_x', **self.size_field_kwargs)]
        if has_size_y:
            size_fieldset_args.append(Field('size_y', **self.size_field_kwargs))
        else:
            del self.fields['size_y']

        size_fieldset_args.append(self.unit_info_html)
        size_fieldset_args.append(Field('unit', **self.unit_field_kwargs))

        self.helper.layout = Layout(
            Div(
                Field('surface', readonly=True, hidden=True),
                Field('data_source', readonly=True, hidden=True),
                Field('name'),
                Field('measurement_date'),
                Field('description'),
                Fieldset(*size_fieldset_args),
                Fieldset('Height Conversion',
                         self.height_scale_info_html,
                         Field('height_scale', **self.height_scale_field_kwargs)),
                Field('detrend_mode'),
                *self.editable_fields,
            ),
            FormActions(
                    Submit('save', 'Save'),
                    HTML("""
                        <a href="{% url 'manager:topography-detail' object.id %}" class="btn btn-default" id="cancel-btn">Cancel</a>
                    """),# TODO check back reference for cancel, always okay like this?
                ),
        )

    datafile = forms.FileInput()
    measurement_date = forms.DateField(input_formats=MEASUREMENT_DATE_INPUT_FORMATS,
                                       help_text=MEASUREMENT_DATE_HELP_TEXT)
    description = forms.Textarea()

    def clean_size_y(self):
        return self._clean_size_element('y')


class SurfaceForm(forms.ModelForm):
    """Form for creating or updating surfaces.
    """

    class Meta:
        model = Surface
        fields = ('name', 'description', 'user')

    helper = FormHelper()
    helper.form_method = 'POST'
    helper.form_show_errors = False  # crispy forms has nicer template code for errors

    helper.layout = Layout(
        Div(
            Field('name'),
            Field('description'),
            Field('user', type="hidden"),
        ),
        FormActions(
                Submit('save', 'Save'),
                HTML("""
                    <a href="{% url 'manager:surface-list' %}" class="btn btn-default" id="cancel-btn">Cancel</a>
                """),# TODO check back reference for cancel
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
        label="Items chosen for selection",
        help_text="""Select one or multiple topographies or surfaces. Search by name.
        A surface represents all its topographies.
        """)

    helper = FormHelper()
    helper.form_method = 'POST'

    helper.layout = Layout(
        Div(
            Field('selection', css_class='col-5'),
            FormActions(
                Submit('save', 'Save selection', css_class='btn-primary'),
                Submit('select-all', 'Select all', css_class='btn-primary'),
                Submit('analyze', 'Save selection & trigger analysis', css_class='btn-primary'),
                HTML("""
                    <a href="{% url 'manager:surface-create' %}" class="btn btn-primary">
                        <i class="fa fa-plus-square-o"></i> Add Surface
                    </a>
                """)
            )
        )
    )

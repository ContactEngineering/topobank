from django.forms import forms, TypedMultipleChoiceField
from django import forms # TODO one form input is ineffective
from django_select2.forms import Select2MultipleWidget

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field, HTML, Div, Fieldset
from crispy_forms.bootstrap import FormActions

from bootstrap_datepicker_plus import DatePickerInput

import logging

from topobank.manager.utils import selection_choices, \
    TopographyFile, TopographyFileReadingException, TopographyFileFormatException
from .models import Topography, Surface

from topobank.users.models import User

_log = logging.getLogger(__name__)

MEASUREMENT_DATE_INPUT_FORMAT = '%Y-%m-%d'
MEASUREMENT_DATE_HELP_TEXT = 'Valid format: "YYYY-mm-dd"'

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
        self._surface = kwargs.pop('surface')
        super(TopographyMetaDataForm, self).__init__(*args, **kwargs)
        self.fields['data_source'] = forms.ChoiceField(choices=data_source_choices)


    helper = FormHelper()
    helper.form_method = 'POST'
    helper.form_show_errors = False  # crispy forms has nicer template code for errors
    helper.form_tag = False

    name = forms.CharField()
    measurement_date = forms.DateField(widget=DatePickerInput(format=MEASUREMENT_DATE_INPUT_FORMAT),
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


    def clean_name(self):
        name = self.cleaned_data['name']

        if Topography.objects.filter(name=name, surface=self._surface).exists():
            msg = f"A topography with same name '{name}' already exists for same surface"
            raise forms.ValidationError(msg, code='duplicate_topography_name_for_same_surface')

        return name


class TopographyUnitsForm(forms.ModelForm):
    """
    This is a base class used to avoid code duplication.
    The form is not directly used.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        helper = FormHelper()
        helper.form_method = 'POST'
        helper.form_show_errors = False  # crispy forms has nicer template code for errors
        helper.form_tag = False

        self.helper = helper

        def info_html(text):
            return HTML("<p><em>"+text+"</em></p>")

        if self.initial['size_editable']:
            self.size_info_html = info_html("Please check this physical size and change it, if needed")

        else:
            self.size_info_html = info_html("Physical size was given in data file and is fixed.")
            self.fields['size_x'].disabled = True

        if self.initial['unit_editable']:
            self.unit_info_html = info_html("Please select the correct unit for the size and height values.")
        else:
            self.unit_info_html = info_html("The unit of the physical size and height scale was given in the " +\
                                            "data file and is fixed.")
            self.fields['unit'].disabled = True

        if self.initial['height_scale_editable']:
            self.height_scale_info_html = info_html("Please enter the correct height scale factor.")

        else:
            self.height_scale_info_html = info_html("The height scale factor was given in the data file and is fixed.")
            self.fields['height_scale'].disabled = True

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
    """
    This form is used when asking for size+units while creating a new 1D topography (line scan).
    """

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
                         Field('size_x'),
                         self.unit_info_html,
                         Field('unit')),
                Fieldset('Height Conversion',
                         self.height_scale_info_html,
                         Field('height_scale')),
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
    """
    This form is used when asking for size+units while creating a new 2D topography.
    """

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

        if not self.initial['size_editable']:
            self.fields['size_y'].disabled = True

        self.helper.layout = Layout(

            Div(
                Fieldset('Physical Size',
                         self.size_info_html,
                         Field('size_x'),
                         Field('size_y'),
                         self.unit_info_html,
                         Field('unit')),
                Fieldset('Height Conversion',
                         self.height_scale_info_html,
                         Field('height_scale')),
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
    """
    This form is used for editing 1D and 2D topographies.
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
                               Field('size_x')]
        if has_size_y:
            size_fieldset_args.append(Field('size_y'))
            if not self.initial['size_editable']:
                self.fields['size_y'].disabled = True
        else:
            del self.fields['size_y']

        size_fieldset_args.append(self.unit_info_html)
        size_fieldset_args.append(Field('unit'))

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
                         Field('height_scale')),
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
    measurement_date = forms.DateField(widget=DatePickerInput(format=MEASUREMENT_DATE_INPUT_FORMAT),
                                       help_text=MEASUREMENT_DATE_HELP_TEXT)
    description = forms.Textarea()

    def clean_size_y(self):
        return self._clean_size_element('y')


class SurfaceForm(forms.ModelForm):
    """Form for creating or updating surfaces.
    """

    class Meta:
        model = Surface
        fields = ('name', 'description', 'category', 'user')

    helper = FormHelper()
    helper.form_method = 'POST'
    helper.form_show_errors = False  # crispy forms has nicer template code for errors

    category = forms.ChoiceField(widget=forms.RadioSelect, choices=Surface.CATEGORY_CHOICES)

    helper.layout = Layout(
        Div(
            Field('name'),
            Field('description'),
            Field('category'),
            Field('user', type="hidden"),
        ),
        FormActions(
                Submit('save', 'Save'),
                HTML("""
                    <a href="{% url 'manager:surface-list' %}" class="btn btn-default" id="cancel-btn">Cancel</a>
                """),# TODO check back reference for cancel
            ),
    )

class SurfaceShareForm(forms.Form):
    """Form for sharing surfaces.
    """

    def __init__(self, *args, **kwargs):
        # user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

        # TODO Solve this with AJAX, we don't want to load all users because of privacy
        self.fields['users'].choices = lambda: [ ("user-{}".format(u.id), u.name)
                                                 for u in User.objects.all()]

    users = TypedMultipleChoiceField(
        required=True,
        widget=Select2MultipleWidget,
        label="Users to share with",
        help_text="""Select one or multiple users you want to give access to this surface.
          Start typing a name in order to find a user. Only registered users can be found.  
          """)

    allow_change = forms.BooleanField(widget=forms.CheckboxInput, required=False,
                                      help_text="""If selected, users will be able to edit meta data
                                      and to add/change/remove individual topographies.""")

    helper = FormHelper()
    helper.form_method = 'POST'

    helper.layout = Layout(
        Div(
            Field('users', css_class='col-7'),
            Field('allow_change'),
            FormActions(
                Submit('save', 'Share this surface', css_class='btn-primary'),
                HTML("""
                <a href="{% url 'manager:surface-detail' surface.pk %}" class="btn btn-default" id="cancel-btn">Cancel</a>
                """),
            )
        )
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

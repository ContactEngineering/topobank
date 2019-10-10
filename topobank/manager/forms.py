from django.forms import forms, TypedMultipleChoiceField, ModelMultipleChoiceField
from django import forms
from django_select2.forms import Select2MultipleWidget, ModelSelect2MultipleWidget

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field, HTML, Div, Fieldset, Button
from crispy_forms.bootstrap import FormActions

from tagulous.forms import TagField

from bootstrap_datepicker_plus import DatePickerInput

import logging

from PyCo.Topography.IO.Reader import CannotDetectFileFormat, CorruptFile, UnknownFileFormatGiven, ReadFileError

from topobank.manager.utils import selection_choices, get_topography_reader
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
            HTML("""
            <a href="{{ cancel_action }}" class="btn btn-default" id="cancel-btn">Cancel</a>
            """),
            # Submit('cancel', 'Cancel', formnovalidate="formnovalidate"),
        ),
    )

    def clean_datafile(self):
        """Do some checks on data file.

        :return:
        """
        #import tempfile # TODO tempfile just for debugging
        #tmpfile = tempfile.NamedTemporaryFile()
        ## try to load topography file, show up error if this doesn't work
        datafile = self.cleaned_data['datafile']
        try:

            #tmpfile.write(datafile.read())
            #tmpfile.seek(0)
            #toporeader = get_topography_reader(tmpfile) # here only the header is checked
            toporeader = get_topography_reader(datafile)

        except UnknownFileFormatGiven as exc:
            msg = f"The format of the given file '{datafile.name}' is unkown. "
            msg += "Please try another file or contact us."
            raise forms.ValidationError(msg, code='invalid_topography_file')
        except CannotDetectFileFormat as exc:
            msg = f"Cannot determine file format of file '{datafile.name}'."
            msg += "Please try another file or contact us."
            raise forms.ValidationError(msg, code='invalid_topography_file')
        except CorruptFile as exc:
            msg = f"File '{datafile.name}' has a known format, but is seems corrupted. "
            msg += "Please check the file or contact us."
            raise forms.ValidationError(msg, code='invalid_topography_file')
        except ReadFileError as exc:
            msg = f"Error while reading file contents of file '{datafile.name}'. "
            if exc.message:
                msg += f"Reason: {exc.message} "

            msg += " Please try another file or contact us."
            _log.info(msg+" Exception: "+str(exc))
            raise forms.ValidationError(msg, code='invalid_topography_file')

        if len(toporeader.channels) == 0:
            raise forms.ValidationError("No topographies found in file.", code='empty_topography_file')

        first_channel_info = toporeader.channels[0]
        if ('dim' in first_channel_info) and (first_channel_info['dim'] > 2):
            raise forms.ValidationError("Number of surface map dimensions > 2.", code='invalid_topography')

        #first_topo = toporeader.topography(channel=0)

        #if first_topo.dim > 2:
        #    raise forms.ValidationError("Number of surface map dimensions > 2.", code='invalid_topography')

        return datafile


class TopographyMetaDataForm(forms.ModelForm):

    class Meta:
        model = Topography
        fields = ('name', 'description', 'measurement_date', 'data_source', 'tags')

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
            Field('tags'),
        ),
        FormActions(
            Submit('save', 'Next'),
            HTML("""
                <a href="{{ cancel_action }}" class="btn btn-default" id="cancel-btn">Cancel</a>
                """),
            # Submit('cancel', 'Cancel', formnovalidate="formnovalidate"),
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

        #
        # Setting defaults for help texts
        #
        help_texts = {
            'size_x': "Please check physical size in x direction and change it, if needed.",
            'size_y': "Please check physical size in y direction and change it, if needed.",
            'unit': "Please select the correct unit for the size and height values.",
            'height_scale': "Please enter the correct height scale factor such that heights match the given unit.",
            'detrend_mode': "The detrending is applied on topography data after reading from data file."
        }

        #
        # Setting the help texts for this form
        #
        if not self.initial['size_editable']:
            help_texts['size_x'] = "Physical size in x direction was given in data file and is fixed."
            help_texts['size_y'] = "Physical size in y direction was given in data file and is fixed."
            self.fields['size_x'].disabled = True
            if "size_y" in self.fields:
                self.fields['size_y'].disabled = True

        if not self.initial['unit_editable']:
            help_texts['unit'] = "The unit of the physical size and height scale was given in the " +\
                                 "data file and is fixed."
            self.fields['unit'].disabled = True

        if not self.initial['height_scale_editable']:
            help_texts['height_scale'] = "The height scale factor was given in the data file and is fixed."
            self.fields['height_scale'].disabled = True

        for fn in help_texts:
            if fn in self.fields:
                self.fields[fn].help_text = help_texts[fn]

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
                         Field('size_x'),
                         Field('unit')),
                Fieldset('Height Conversion',
                         Field('height_scale')),
                Field('detrend_mode'),
                Field('resolution_x', type="hidden"),  # only in order to have the data in wizard's .done() method
                *self.editable_fields,
            ),
            FormActions(
                Submit('save', 'Save new topography'),
                HTML("""
                  <a href="{{ cancel_action }}" class="btn btn-default" id="cancel-btn">Cancel</a>
                """),
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

        self.helper.layout = Layout(

            Div(
                Fieldset('Physical Size',
                         Field('size_x'),
                         Field('size_y'),
                         Field('unit')),
                Fieldset('Height Conversion',
                         Field('height_scale')),
                Field('detrend_mode'),
                Field('resolution_x', type="hidden"), # only in order to have the data in wizard's .done() method
                Field('resolution_y', type="hidden"), # only in order to have the data in wizard's .done() method
                *self.editable_fields,
            ),
            FormActions(
                Submit('save', 'Save new topography'),
                HTML("""
                    <a href="{{ cancel_action }}" class="btn btn-default" id="cancel-btn">Cancel</a>
                    """),
                # Submit('cancel', 'Cancel', formnovalidate="formnovalidate"),
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
                  'name', 'description',
                  'measurement_date', 'tags',
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
                               Field('size_x')]
        if has_size_y:
            size_fieldset_args.append(Field('size_y'))
            if not self.initial['size_editable']:
                self.fields['size_y'].disabled = True
        else:
            del self.fields['size_y']

        size_fieldset_args.append(Field('unit'))

        self.helper.layout = Layout(
            Div(
                Field('surface', readonly=True, hidden=True),
                Field('data_source', readonly=True, hidden=True),
                Field('name'),
                Field('measurement_date'),
                Field('description'),
                Field('tags'),
                Fieldset(*size_fieldset_args),
                Fieldset('Height Conversion',
                         Field('height_scale')),
                Field('detrend_mode'),
                *self.editable_fields,
            ),
            FormActions(
                    Submit('save-stay', 'Save and keep editing'),
                    Submit('save-finish', 'Save and finish editing'),
                    HTML("""
                        <a href="{% url 'manager:topography-detail' object.id %}" class="btn btn-default" id="cancel-btn">
                        Finish editing without saving</a>
                    """),
                ),
        )

    datafile = forms.FileInput()
    measurement_date = forms.DateField(widget=DatePickerInput(format=MEASUREMENT_DATE_INPUT_FORMAT),
                                       help_text=MEASUREMENT_DATE_HELP_TEXT)
    description = forms.Textarea()

    tags = TagField()

    def clean_size_y(self):
        return self._clean_size_element('y')


class SurfaceForm(forms.ModelForm):
    """Form for creating or updating surfaces.
    """

    class Meta:
        model = Surface
        fields = ('name', 'description', 'category', 'creator', 'tags')

    helper = FormHelper()
    helper.form_method = 'POST'
    helper.form_show_errors = False  # crispy forms has nicer template code for errors

    category = forms.ChoiceField(widget=forms.RadioSelect, choices=Surface.CATEGORY_CHOICES)
    # tags = TagField(widget=Select2MultipleWidget)

    helper.layout = Layout(
        Div(
            Field('name'),
            Field('description'),
            Field('category'),
            Field('tags'),
            Field('creator', type="hidden"),
        ),
        FormActions(
                Submit('save', 'Save'),
                HTML("""
                    <a class="btn btn-default" id="cancel-btn" onclick="history.back(-1)">Cancel</a>
                """),
            ),
    )

class MultipleUserSelectWidget(ModelSelect2MultipleWidget):
    model = User
    search_fields = ['name']
    max_results = 10

    def filter_queryset(self, request, term, queryset=None, **dependent_fields):

        #
        # Type at least a number of letters before first results are shown
        #
        if len(term)<SurfaceShareForm.SHARING_MIN_LETTERS_FOR_USER_DISPLAY:
            return queryset.none()

        #
        # Exclude anonymous user and requesting user
        #
        return queryset.filter(name__icontains=term)\
            .exclude(username='AnonymousUser')\
            .exclude(id=request.user.id)\
            .order_by('name')

class SurfaceShareForm(forms.Form):
    """Form for sharing surfaces.
    """

    # minimum number of letters to type until a user name is displayed
    SHARING_MIN_LETTERS_FOR_USER_DISPLAY = 3

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    users = ModelMultipleChoiceField(
        required=True,
        queryset=User.objects,
        widget=MultipleUserSelectWidget,
        label="Users to share with",
        help_text="""<b>Type at least {} characters to start a search.</b>
          Select one or multiple users you want to give access to this surface.  
          """.format(SHARING_MIN_LETTERS_FOR_USER_DISPLAY))

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
                HTML("""
                    <a href="{% url 'manager:surface-create' %}" class="btn btn-primary">
                        <i class="fa fa-plus-square-o"></i> Add Surface
                    </a>
                """)
            )
        )
    )

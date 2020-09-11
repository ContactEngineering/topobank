from django.forms import forms, ModelMultipleChoiceField
from django import forms
from django_select2.forms import ModelSelect2MultipleWidget

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field, HTML, Div, Fieldset
from crispy_forms.bootstrap import FormActions

from tagulous.forms import TagField

from bootstrap_datepicker_plus import DatePickerInput

import logging

from SurfaceTopography.IO.Reader import CannotDetectFileFormat, CorruptFile, UnknownFileFormatGiven, ReadFileError

from topobank.manager.utils import get_topography_reader
from .models import Topography, Surface, MAX_LENGTH_DATAFILE_FORMAT

from topobank.users.models import User

_log = logging.getLogger(__name__)

MEASUREMENT_DATE_INPUT_FORMAT = '%Y-%m-%d'
MEASUREMENT_DATE_HELP_TEXT = 'Valid format: "YYYY-mm-dd"'
ASTERISK_HELP_HTML = HTML("<p>Fields marked with an asterisk (*) are mandatory.</p>")
TAGS_HELP_TEXT = "You can choose existing tags or create new tags on-the-fly. "+\
                 "Use '/' character to build hierarchies, e.g. 'fruit/apple'."
DEFAULT_LICENSE = 'ccbysa-4.0'

################################################################
# Topography Forms
################################################################


class TopographyFileUploadForm(forms.ModelForm):

    class Meta:
        model = Topography
        fields = ('datafile', 'datafile_format', 'surface')

    helper = FormHelper()
    helper.form_method = 'POST'
    helper.form_show_errors = False  # crispy forms has nicer template code for errors
    helper.form_tag = False  # we use an own form tag with the wizard

    datafile = forms.FileField()

    helper.layout = Layout(
        Div(
            HTML('You are about to add a topography to surface <em>{{ surface.name }}</em>.'),
            Field('datafile'),
            Field('datafile_format', type='hidden'),  # in order to have data later in wizard's done() method
            Field('surface', type='hidden')  # in order to have data later in wizard's done() method
        ),
        FormActions(
            Submit('save', 'Next'),
            HTML("""
            <a href="{{ cancel_action }}" class="btn btn-default" id="cancel-btn">Cancel</a>
            """),
        ),
        ASTERISK_HELP_HTML
    )

    def clean(self):
        cleaned_data = super().clean()

        try:
            datafile = cleaned_data['datafile']
        except KeyError:
            raise forms.ValidationError("Cannot proceed without given a data file.", code='invalid_topography_file')

        #
        # Check whether file can be loaded and has all necessary meta data
        #
        try:
            toporeader = get_topography_reader(datafile)
            datafile_format = toporeader.format()
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

        if len(datafile_format) > MAX_LENGTH_DATAFILE_FORMAT:
            raise forms.ValidationError("Too long name for datafile format: '%(fmt)s'. At maximum %(maxlen)d characters allowed.",
                                        params=dict(fmt=datafile_format, maxlen=MAX_LENGTH_DATAFILE_FORMAT),
                                        code='too_long_datafile_format')

        cleaned_data['datafile_format'] = datafile_format

        if len(toporeader.channels) == 0:
            raise forms.ValidationError("No topographies found in file.", code='empty_topography_file')

        #
        # Check all channels for having correct keys
        #
        for channel_index, channel_info in enumerate(toporeader.channels):

            try:
                dim = int(channel_info.dim)
            except:
                raise forms.ValidationError("Cannot interpret number of dimensions for channel no. " +
                                            f"{channel_index}: {channel_info.dim}",
                                            code='invalid_topography')
            if dim > 2:
                raise forms.ValidationError(f"Number of dimensions for channel no. {channel_index} > 2.",
                                            code='invalid_topography')


            numbers = channel_info.nb_grid_pts

            try:
                numbers = tuple(numbers)
            except:
                raise forms.ValidationError("Cannot interpret number of grid points for channel no. " +
                                            f"{channel_index} as tuple: {channel_info.nb_grid_pts}",
                                            code='invalid_topography')
            for n in numbers:
                try:
                    n = int(n)
                except:
                    raise forms.ValidationError("Cannot interpret number of grid points for channel no. " +
                                                f"{channel_index}: {channel_info.nb_grid_pts}",
                                                code='invalid_topography')
                if n <= 0:
                    raise forms.ValidationError("Number of grid points must be a positive number > 0." +
                                                f" (channel: {channel_index})", code='invalid_topography')

        return cleaned_data



class TopographyMetaDataForm(forms.ModelForm):

    class Meta:
        model = Topography
        fields = ('name', 'description', 'measurement_date', 'data_source', 'tags')

    def __init__(self, *args, **kwargs):
        data_source_choices = kwargs.pop('data_source_choices')
        autocomplete_tags = kwargs.pop('autocomplete_tags')
        self._surface = kwargs.pop('surface')
        super(TopographyMetaDataForm, self).__init__(*args, **kwargs)
        self.fields['data_source'] = forms.ChoiceField(choices=data_source_choices)

        self.fields['tags'] = TagField(required=False, autocomplete_tags=autocomplete_tags,
                                       help_text=TAGS_HELP_TEXT)

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
        ASTERISK_HELP_HTML
    )

    def clean_name(self):
        name = self.cleaned_data['name']

        if Topography.objects.filter(name=name, surface=self._surface).exists():
            msg = f"A topography with same name '{name}' already exists for same surface"
            raise forms.ValidationError(msg, code='duplicate_topography_name_for_same_surface')

        return name


def make_is_periodic_field():
    """Generate a boolean field which can be used for "is_periodic" field in several forms.

    :return: forms.BooleanField instance
    """
    return forms.BooleanField(widget=forms.CheckboxInput, required=False,
                              label='This topography should be considered periodic in terms of a repeating array'
                                    ' of the uploaded data',
                              help_text="""<b>Can only be enabled for 2D topographies and if no sizes were given in
                                    original file.</b>
                                    When enabled, this affects analysis results like PSD or ACF.
                                    No detrending can be used for periodic topographies, except of
                                    substracting the mean height.
                                    Additionally, the default calculation type for contact mechanics
                                    will be set to 'periodic'. """)

class TopographyUnitsForm(forms.ModelForm):
    """
    This is a base class used to avoid code duplication.
    The form is not directly used.
    """

    is_periodic = make_is_periodic_field()

    def __init__(self, *args, **kwargs):
        self._allow_periodic = kwargs.pop('allow_periodic')
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

        #
        # For certain cases like line scans we need to disable the periodic checkbox
        #
        self.fields['is_periodic'].disabled = not self._allow_periodic

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

    def clean_detrend_mode(self):
        #
        # If topography should be periodic, only detrend mode 'center' is allowed.
        #
        cleaned_data = super().clean()

        if cleaned_data['is_periodic'] and (cleaned_data['detrend_mode'] != 'center'):
            raise forms.ValidationError("When enabling periodicity only detrend mode "+\
                                        f"'{Topography.DETREND_MODE_CHOICES[0][1]}' is a valid option. "+\
                                        "Either choose that option or disable periodicity (see checkbox).")
        return cleaned_data['detrend_mode']


class TopographyWizardUnitsForm(TopographyUnitsForm):
    """
    This form is used for editing units of 1D and 2D topographies in the topography wizard.
    """

    class Meta:
        model = Topography
        fields = ('size_editable',
                  'unit_editable',
                  'height_scale_editable',
                  'size_x', 'size_y',
                  'unit', 'is_periodic',
                  'height_scale', 'detrend_mode',
                  'resolution_x', 'resolution_y')

    def __init__(self, *args, **kwargs):
        has_size_y = kwargs.pop('has_size_y')

        super().__init__(*args, **kwargs)

        self.helper.form_tag = True

        size_fieldset_args = ['Physical Size',
                               Field('size_x')]
        resolution_fieldset_args = [Field('resolution_x', type="hidden")]
        # resolution is handled here only in order to have the data in wizard's .done() method

        if has_size_y:
            size_fieldset_args.append(Field('size_y'))
            if not self.initial['size_editable']:
                self.fields['size_y'].disabled = True
            resolution_fieldset_args.append(Field('resolution_y', type="hidden"))
        else:
            del self.fields['size_y']
            del self.fields['resolution_y']

        size_fieldset_args.append(Field('unit'))
        size_fieldset_args.append(Field('is_periodic'))

        self.helper.layout = Layout(
            Div(
                Fieldset(*size_fieldset_args),
                Fieldset('Height Conversion',
                         Field('height_scale')),
                Field('detrend_mode'),
                *self.editable_fields,
                *resolution_fieldset_args
            ),
            FormActions(
                Submit('save', 'Save new topography'),
                HTML("""<a href="{{ cancel_action }}" class="btn btn-default" id="cancel-btn">Cancel</a>"""),
                ),
            ASTERISK_HELP_HTML
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
                  'size_x', 'size_y',
                  'unit', 'is_periodic',
                  'height_scale', 'detrend_mode',
                  'surface')

    def __init__(self, *args, **kwargs):
        has_size_y = kwargs.pop('has_size_y')
        autocomplete_tags = kwargs.pop('autocomplete_tags')
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
        size_fieldset_args.append(Field('is_periodic'))

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
            ASTERISK_HELP_HTML
        )
        self.fields['tags'] = TagField(
            required=False,
            autocomplete_tags=autocomplete_tags,  # set special values for user
            help_text=TAGS_HELP_TEXT,
        )

    datafile = forms.FileInput()
    measurement_date = forms.DateField(widget=DatePickerInput(format=MEASUREMENT_DATE_INPUT_FORMAT),
                                       help_text=MEASUREMENT_DATE_HELP_TEXT)
    description = forms.Textarea()

    is_periodic = make_is_periodic_field()

    def clean_size_y(self):
        return self._clean_size_element('y')


class SurfaceForm(forms.ModelForm):
    """Form for creating or updating surfaces.
    """

    class Meta:
        model = Surface
        fields = ('name', 'description', 'category', 'creator', 'tags')

    def __init__(self, *args, **kwargs):
        autocomplete_tags = kwargs.pop('autocomplete_tags')
        super().__init__(*args, **kwargs)

        self.fields['tags'] = TagField(
            required=False,
            autocomplete_tags=autocomplete_tags,  # set special values for user
            help_text=TAGS_HELP_TEXT,
        )

    helper = FormHelper()
    helper.form_method = 'POST'
    helper.form_show_errors = False  # crispy forms has nicer template code for errors

    category = forms.ChoiceField(widget=forms.RadioSelect, choices=Surface.CATEGORY_CHOICES)

    helper.layout = Layout(
        Div(
            Field('name'),
            Field('description'),
            Field('category'),
            Field('tags'),
            Field('creator', type='hidden')
        ),
        FormActions(
                Submit('save', 'Save'),
                HTML("""
                    <a class="btn btn-default" id="cancel-btn" onclick="history.back(-1)">Cancel</a>
                """),
            ),
        ASTERISK_HELP_HTML
    )


class MultipleUserSelectWidget(ModelSelect2MultipleWidget):
    model = User
    search_fields = ['name']
    max_results = 10

    def filter_queryset(self, request, term, queryset=None, **dependent_fields):

        #
        # Type at least a number of letters before first results are shown
        #
        if len(term) < SurfaceShareForm.SHARING_MIN_LETTERS_FOR_USER_DISPLAY:
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
        widget=MultipleUserSelectWidget(attrs={'data-minimum-input-length': SHARING_MIN_LETTERS_FOR_USER_DISPLAY}),
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
            HTML("Would you like to share the surface <em>{{ surface.name }}</em> with other users?"),
            Field('users', css_class='col-7'),
            Field('allow_change'),
            FormActions(
                Submit('save', 'Share this surface', css_class='btn-primary'),
                HTML("""
                <a href="{% url 'manager:surface-detail' surface.pk %}" class="btn btn-default" id="cancel-btn">Cancel</a>
                """),
            ),
            ASTERISK_HELP_HTML
        )
    )


class SurfacePublishForm(forms.Form):
    """Form for publishing surfaces."""

    helper = FormHelper()
    helper.form_method = 'POST'

    license = forms.ChoiceField(widget=forms.RadioSelect, choices=Surface.LICENSE_CHOICES,
                                required=True)

    agreed = forms.BooleanField(widget=forms.CheckboxInput, required=True,
                                label="I understand the implications of publishing this surface and I agree.",
                                help_text="""Please read the implications of publishing listed above and check.""")

    copyright_hold = forms.BooleanField(widget=forms.CheckboxInput, required=True,
                                label="I hold copyright of this data or have been authorized by the copyright holders.",
                                help_text="""Please make sure you're not publishing data """
                                        """from others without their authorization.""")

    helper.layout = Layout(
        Div(
            FormActions(
                Fieldset('Please choose a license',
                         Field('license', template="manager/license_radioselect.html")
                ),
                Fieldset('Final checks',
                         Field('agreed'),
                         Field('copyright_hold'),
                ),
                Submit('save', 'Yes, publish this surface', css_class='btn-success'),
                HTML("""
                <a href="{% url 'manager:surface-detail' surface.pk %}" class="btn btn-default" id="cancel-btn">Cancel</a>
                """),
            ),
            ASTERISK_HELP_HTML
        )
    )



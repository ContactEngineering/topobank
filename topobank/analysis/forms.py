from django.forms import ModelMultipleChoiceField, forms
from django_select2.forms import Select2MultipleWidget
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field, HTML, Div, Hidden, Fieldset
from crispy_forms.bootstrap import (TabHolder, Tab, FormActions, InlineRadios)

from ..manager.models import Topography
from .models import AnalysisFunction


class TopographyFunctionSelectForm(forms.Form):

    topographies = ModelMultipleChoiceField(queryset=Topography.objects.all(),
                                            widget=Select2MultipleWidget,
                                            label="Topographies",
                                            help_text="Select one or multiple topographies. Search by name.")
    functions = ModelMultipleChoiceField(queryset=AnalysisFunction.objects.all(),
                                         widget=Select2MultipleWidget,
                                         label="Functions",
                                         help_text="Select one or multiple analysis functions. Search by name.")

    # TODO select only Topographies from current user

    helper = FormHelper()
    helper.form_method = 'POST'

    # helper.form_class = 'form-horizontal'
    #helper.label_class = 'col-sm-2'
    # helper.field_class = 'col-sm-6'

    helper.layout = Layout(
        Field('topographies'),
        Field('functions'),
        FormActions(
            Submit('save', 'Save selection and update results', css_class='btn-primary'),
        ),
    )




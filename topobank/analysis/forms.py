from django.forms import ModelMultipleChoiceField, forms, CheckboxSelectMultiple, MultipleChoiceField

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, HTML, Div
from crispy_forms.bootstrap import (FormActions, InlineCheckboxes)

from .models import AnalysisFunction

from .registry import AnalysisRegistry

class FunctionSelectForm(forms.Form):
    """Form for selecting an analysis function."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['functions'].label = False

    help_text = "Select one or multiple analysis functions."

    function_names = AnalysisRegistry().get_analysis_function_names()

    function_qs = AnalysisFunction.objects.filter(name__in=function_names).order_by('name')
    functions = ModelMultipleChoiceField(queryset=function_qs,
                                         widget=CheckboxSelectMultiple,
                                         help_text=help_text)

    helper = FormHelper()
    helper.form_method = 'POST'

    helper.layout = Layout(
        Div(
            InlineCheckboxes('functions'),
            FormActions(
                Submit('save', 'Update results', css_class='btn btn-primary'),
            ),
            HTML('<hr/>'),
        )
    )

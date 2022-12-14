from django.forms import ModelMultipleChoiceField, forms, CheckboxSelectMultiple, MultipleChoiceField

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, HTML, Div
from crispy_forms.bootstrap import (FormActions, InlineCheckboxes)

from .models import AnalysisFunction

from .registry import AnalysisRegistry

class FunctionSelectForm(forms.Form):
    """Form for selecting an analysis function."""

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user")
        super().__init__(*args, **kwargs)

        function_names = AnalysisRegistry().get_analysis_function_names(user)
        function_qs = AnalysisFunction.objects.filter(name__in=function_names).order_by('name')

        help_text = "Select one or multiple analysis functions." if function_names \
            else "Sorry, no analysis functions available."
        self.fields['functions'] = ModelMultipleChoiceField(
          queryset=function_qs,
          widget=CheckboxSelectMultiple,
          help_text=help_text
        )
        self.fields['functions'].label = False


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

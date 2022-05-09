from django.forms import ModelMultipleChoiceField, forms, CheckboxSelectMultiple
from django.contrib.contenttypes.models import ContentType

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, HTML, Div
from crispy_forms.bootstrap import (FormActions, InlineCheckboxes)

from .models import AnalysisFunction


class FunctionSelectForm(forms.Form):
    """Form for selecting an analysis function."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['functions'].label = False

    help_text = "Select one or multiple analysis functions."

    functions = ModelMultipleChoiceField(queryset=AnalysisFunction.objects.order_by('name'),
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

from django.forms import ModelMultipleChoiceField, forms, CheckboxSelectMultiple

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, HTML, Div
from crispy_forms.bootstrap import (FormActions, InlineCheckboxes)

from .models import AnalysisFunction

class FunctionSelectForm(forms.Form):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['functions'].label = False

    functions = ModelMultipleChoiceField(queryset=AnalysisFunction.objects.all(),
                                         widget=CheckboxSelectMultiple,
                                         help_text="Select one or multiple analysis functions.")

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




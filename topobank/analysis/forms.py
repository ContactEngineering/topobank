from django.forms import ModelMultipleChoiceField, forms, CheckboxSelectMultiple

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, HTML, Div
from crispy_forms.bootstrap import (FormActions, InlineCheckboxes)

from .models import AnalysisFunction

class FunctionSelectForm(forms.Form):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['functions'].label = "" # we set our own label in larger font

    functions = ModelMultipleChoiceField(queryset=AnalysisFunction.objects.all(),
                                         widget=CheckboxSelectMultiple,
                                         label="Functions",
                                         help_text="Select one or multiple analysis functions.")

    helper = FormHelper()
    helper.form_method = 'POST'

    helper.layout = Layout(
        Div(
            HTML('<h5>Functions</h5>'),
            InlineCheckboxes('functions'),
            HTML('<hr/>'),
            FormActions(
                Submit('save', 'Update results', css_class='btn btn-primary'),
            ),
        )
    )




from django.forms import ModelMultipleChoiceField, forms, CheckboxSelectMultiple
from django.contrib.contenttypes.models import ContentType

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, HTML, Div
from crispy_forms.bootstrap import (FormActions, InlineCheckboxes)

from .models import AnalysisFunction
from ..manager.models import Surface


class FunctionChoiceField(ModelMultipleChoiceField):
    """Field for choosing an Analysis function.

    Subclassed here for added a custom representation including the implemented types.
    """
    def label_from_instance(self, function):
        """Return a custom representation based on an instance."""
        label = str(function)

        if function.is_implemented_for_type(ContentType.objects.get_for_model(Surface)):
            label = "(Average) "+label

        return label


class FunctionSelectForm(forms.Form):
    """Form for selecting an analysis function."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['functions'].label = False

    help_text = "Select one or multiple analysis functions. Functions annotated with '(Average)' also " \
                "show an average for all measurements for a surface if there is more than one."

    functions = FunctionChoiceField(queryset=AnalysisFunction.objects.all(),
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




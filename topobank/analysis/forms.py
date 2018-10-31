from django.forms import ModelMultipleChoiceField, forms, TypedMultipleChoiceField
from django_select2.forms import Select2MultipleWidget
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field, HTML, Div, Hidden, Fieldset, Row, Column
from crispy_forms.bootstrap import (TabHolder, Tab, FormActions, InlineRadios)

from ..manager.utils import selection_choices
from .models import AnalysisFunction

class TopographyFunctionSelectForm(forms.Form):

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

        self.fields['selection'].choices = lambda: selection_choices(user)

    selection = TypedMultipleChoiceField( # TODO remove dupliate code, compare with manager.forms
        widget=Select2MultipleWidget,
        label="Chosen Topographies",
        help_text="""Select one or multiple topographies or surfaces. Search by name.
                  A surface represents all its topographies.
                  """)

    functions = ModelMultipleChoiceField(queryset=AnalysisFunction.objects.all(),
                                         widget=Select2MultipleWidget,
                                         label="Functions",
                                         help_text="Select one or multiple analysis functions. Search by name.")

    helper = FormHelper()
    helper.form_method = 'POST'

    helper.layout = Layout(
        Div(
            Field('selection', css_class='col-5'),
            Field('functions', css_class='col-5'),
            FormActions(
                Submit('save', 'Save selection and update results', css_class='btn btn-primary'),
            ),
        )
    )




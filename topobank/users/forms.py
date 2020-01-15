from allauth.account.forms import SignupForm
from django import forms


class SignupFormWithName(SignupForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'] = forms.CharField()


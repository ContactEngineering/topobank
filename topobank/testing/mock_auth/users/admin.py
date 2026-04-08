from django import forms

from .models import User


class MyUserCreationForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('username',)

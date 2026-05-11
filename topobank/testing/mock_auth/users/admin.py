from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm


class MyUserCreationForm(UserCreationForm):
    error_messages = dict(
        UserCreationForm.error_messages,
        duplicate_username="This username has already been taken.",
    )

    class Meta(UserCreationForm.Meta):
        model = get_user_model()

    def clean_username(self):
        username = self.cleaned_data["username"]
        User = get_user_model()
        try:
            User.objects.get(username=username)
        except User.DoesNotExist:
            return username

        raise forms.ValidationError(self.error_messages["duplicate_username"])

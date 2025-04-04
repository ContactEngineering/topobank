from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.core.exceptions import ValidationError
from django.urls import NoReverseMatch, reverse

try:
    ACCOUNT_SIGNUP_URL = reverse("account_signup")
except NoReverseMatch:
    ACCOUNT_SIGNUP_URL = None


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        # See: https://github.com/pennersr/django-allauth/issues/345
        if ACCOUNT_SIGNUP_URL is not None and request.path.rstrip(
            "/"
        ) == ACCOUNT_SIGNUP_URL.rstrip("/"):
            return False
        return True

    def save_user(self, request, user, form, commit=True):
        """
        This is called when saving user via allauth registration.
        We override this to set additional data on user object.
        """
        # Do not persist the user yet so we pass commit=False
        # (last argument)
        user = super().save_user(request, user, form, commit=False)
        user.name = form.cleaned_data.get("name")
        user.save()


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def validate_disconnect(self, account, accounts):
        raise ValidationError("Can not disconnect social account")

from django.apps import AppConfig


class UsersAppConfig(AppConfig):
    name = "topobank.users"
    verbose_name = "Users"

    def ready(self):
        """Override this to put in:
            Users system checks
            Users signal registration
        """
        import topobank.users.signals  # noqa: F401

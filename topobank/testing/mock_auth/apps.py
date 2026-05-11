from django.apps import AppConfig


class UsersAppConfig(AppConfig):
    name = 'topobank.testing.mock_auth.users'
    label = 'users'


class AuthorizationAppConfig(AppConfig):
    name = 'topobank.testing.mock_auth.authorization'
    label = 'authorization'


class OrganizationsAppConfig(AppConfig):
    name = 'topobank.testing.mock_auth.organizations'
    label = 'organizations'

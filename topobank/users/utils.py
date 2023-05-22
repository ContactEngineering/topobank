from django.contrib.auth.models import Group

from .models import DEFAULT_GROUP_NAME


def are_collaborating(user1, user2):
    """Returns True if given users are collaborating, e.g. sharing sth.

    A user also collaborates with himself (hopefully).

    :param user1: User instance
    :param user2: User instance
    :return: True if collaborators, else False
    """
    return (user1 == user2) or user1.is_sharing_with(user2) or user2.is_sharing_with(user1)


def get_default_group():
    group, created = Group.objects.get_or_create(name=DEFAULT_GROUP_NAME)
    return group

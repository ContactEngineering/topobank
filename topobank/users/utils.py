
def are_collaborating(user1, user2):
    """Returns True if given users are collaborating, e.g. sharing sth.

    A user also collaborates with himself (hopefully).

    :param user1: User instance
    :param user2: User instance
    :return: True if collaborators, else False
    """
    return (user1 == user2) or user1.is_sharing_with(user2) or user2.is_sharing_with(user1)


def register_metrics():
    """Register metrics which can be used to track events.

    Returns
    -------

    """
    from trackstats.models import Domain, Metric

    Domain.objects.USERS = Domain.objects.register(
        ref='users',
        name='Users'
    )
    Metric.objects.USERS_LOGIN_COUNT = Metric.objects.register(
        domain=Domain.objects.USERS,
        ref='login_count',
        name='Number of users logged in'
    )

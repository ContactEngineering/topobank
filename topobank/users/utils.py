
def are_collaborating(user1, user2):
    """Returns True if given users are collaborating, e.g. sharing sth.

    A user also collaborates with himself (hopefully).

    :param user1: User instance
    :param user2: User instance
    :return: True if collaborators, else False
    """
    return (user1 == user2) or user1.is_sharing_with(user2) or user2.is_sharing_with(user1)

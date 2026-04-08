def get_anonymous_user():
    from .models import User
    user, created = User.objects.get_or_create(username="anonymous")
    return user

from ..organizations.models import Organization
from ..users.models import User
from .models import ViewEditFull, ViewEditFullNone


class PermissionMixin:
    def get_permission(self, user: User) -> ViewEditFullNone:
        perm = self.permissions.get_for_user(user)
        if perm is None:
            return None
        else:
            return perm

    def grant_permission(self, user: User | Organization, allow: ViewEditFull = "view"):
        self.permissions.grant(user, allow)

    def revoke_permission(self, user: User | Organization):
        self.permissions.revoke(user)

    def has_permission(self, user: User, access_level: ViewEditFull = "view") -> bool:
        return self.permissions.user_has_permission(user, access_level)

    def authorize_user(self, user: User, access_level: ViewEditFull = "view"):
        self.permissions.authorize_user(user, access_level)

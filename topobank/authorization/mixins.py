from .models import ViewEditFull, ViewEditFullNone


class PermissionMixin:
    def get_permission(self, user) -> ViewEditFullNone:
        perm = self.permissions.get_for_user(user)
        if perm is None:
            return None
        else:
            return perm

    def grant_permission(self, principal, allow: ViewEditFull = "view"):
        self.permissions.grant(principal, allow)

    def revoke_permission(self, principal):
        self.permissions.revoke(principal)

    def has_permission(self, user, access_level: ViewEditFull = "view") -> bool:
        return self.permissions.user_has_permission(user, access_level)

    def authorize_user(self, user, access_level: ViewEditFull = "view"):
        self.permissions.authorize_user(user, access_level)

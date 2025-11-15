from topobank.authorization.permissions import ObjectPermission


class ManifestPermission(ObjectPermission):
    def has_object_permission(self, request, view, obj):
        # If this manifest is part of a folder and that folder is set to read-only,
        # then deny all write accesses
        if obj.folder and obj.folder.read_only:
            if request.method not in ["GET", "HEAD", "OPTIONS"]:
                return False
        return super().has_object_permission(request, view, obj)

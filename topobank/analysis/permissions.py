from rest_framework.permissions import BasePermission


class WorkflowPermissions(BasePermission):
    def has_object_permission(self, request, view, obj):
        # This only works for Workflow models
        return obj.has_permission(request.user)

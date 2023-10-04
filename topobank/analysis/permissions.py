from rest_framework.permissions import BasePermission


class AnalysisFunctionPermissions(BasePermission):
    def has_object_permission(self, request, view, obj):
        # This only works for AnalysisFunction models
        return obj.is_available_for_user(request.user)

from django.db.models import Q
from rest_framework import viewsets
from rest_framework.pagination import LimitOffsetPagination

from .anonymous import get_anonymous_user
from .models import User
from .permissions import UserPermission
from .serializers import UserSerializer


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    pagination_class = LimitOffsetPagination
    permission_classes = [UserPermission]

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return User.objects.none()

        name = self.request.query_params.get("name")

        # We don't want the anonymous user
        qs = User.objects.exclude(id=get_anonymous_user().id)

        # If we are not the staff user, then only show users of organizations
        # the current user is a member of
        if not self.request.user.is_staff:
            qs = qs.filter(groups__in=self.request.user.groups.all())

        # Filter for name
        if name is not None:
            qs = qs.filter(name__icontains=name)
        
        # Return query set
        return qs
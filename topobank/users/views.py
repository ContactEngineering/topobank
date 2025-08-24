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
        name = self.request.query_params.get("name")
        max_results = int(self.request.query_params.get("max", 5))
        if name is None:
            if self.request.user.is_authenticated:
                return User.objects.all()
            else:
                return User.objects.none()
        else:
            return User.objects.filter(
                Q(name__icontains=name) & ~Q(id=get_anonymous_user().id)
            )[0:max_results]

from django.db.models import Q
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticatedOrReadOnly

from .anonymous import get_anonymous_user
from .models import User
from .serializers import UserSerializer


class UserViewSet(
    mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

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

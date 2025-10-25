from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response

from ..organizations.models import resolve_organization
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
        organization = self.request.query_params.get("organization")

        # We don't want the anonymous user
        qs = User.objects.exclude(id=get_anonymous_user().id)

        # If we are not the staff user, then only show users of organizations
        # the current user is a member of
        if not self.request.user.is_staff:
            qs = qs.filter(
                Q(id=self.request.user.id)
                | Q(groups__in=self.request.user.groups.all())
            )

        # Filter for name
        if name is not None:
            qs = qs.filter(name__icontains=name)

        # Filter for organization
        if organization is not None:
            qs = qs.filter(groups__organization=organization)

        # Return query set
        return qs


def get_user_and_organization(request, pk):
    user = get_object_or_404(User, pk=pk)
    organization_url = request.data.get("organization")
    organization = resolve_organization(organization_url)
    return user, organization


@api_view(["POST"])
@permission_classes([UserPermission])
def add_organization(request, pk: int):
    user, organization = get_user_and_organization(request, pk)
    user.groups.add(organization.group)
    return Response({})


@api_view(["POST"])
@permission_classes([UserPermission])
def remove_organization(request, pk: int):
    user, organization = get_user_and_organization(request, pk)
    user.groups.remove(organization.group)
    return Response({})

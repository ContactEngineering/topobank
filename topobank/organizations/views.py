from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response

from ..users.models import resolve_user
from .models import Organization
from .permissions import OrganizationPermission
from .serializers import OrganizationSerializer


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSerializer
    pagination_class = LimitOffsetPagination
    permission_classes = [OrganizationPermission]

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Organization.objects.none()

        user = self.request.query_params.get("user", None)

        if self.request.user.is_staff:
            # Staff users can see all organizations
            qs = Organization.objects.all()
        else:
            # Normal users can only see organizations they are member of
            qs = Organization.objects.filter(
                group__in=self.request.user.groups.all()
            )

        # Filter for specific user
        if user is not None:
            qs = qs.filter(group__user=user)

        # Return query set
        return qs.distinct()


def get_user_and_organization(request, pk):
    organization = Organization.objects.get(pk=pk)
    user_url = request.data.get("user")
    user = resolve_user(user_url)
    return user, organization


@api_view(["POST"])
@permission_classes([OrganizationPermission])
def add_user(request, pk: int):
    user, organization = get_user_and_organization(request, pk)
    user.groups.add(organization.group)
    return Response({})


@api_view(["POST"])
@permission_classes([OrganizationPermission])
def remove_user(request, pk: int):
    user, organization = get_user_and_organization(request, pk)
    user.groups.remove(organization.group)
    return Response({})

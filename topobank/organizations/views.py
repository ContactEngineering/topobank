from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from topobank.supplib.pagination import TopobankPaginator

from ..users.models import resolve_user
from .models import Organization
from .permissions import OrganizationPermission
from .serializers import OrganizationSerializer


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSerializer
    pagination_class = TopobankPaginator
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

    @transaction.atomic
    def perform_create(self, serializer):
        serializer.save()

    @transaction.atomic
    def perform_update(self, serializer):
        serializer.save()

    @transaction.atomic
    def perform_destroy(self, instance):
        instance.delete()


def get_user_and_organization(request, pk):
    organization = get_object_or_404(Organization, pk=pk)
    user_url = request.data.get("user")
    user = resolve_user(user_url)
    return user, organization


@extend_schema(
    description="Add a user to an organization",
    parameters=[
        OpenApiParameter(
            name="pk",
            type=int,
            location=OpenApiParameter.PATH,
            description="Organization ID",
        ),
    ],
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.NONE},
)
@api_view(["POST"])
@permission_classes([OrganizationPermission])
@transaction.atomic
def add_user(request, pk: int):
    user, organization = get_user_and_organization(request, pk)

    # Explicit object-level permission check
    permission = OrganizationPermission()
    if not permission.has_object_permission(request, None, organization):
        return HttpResponseForbidden("You do not have permission to modify this organization.")

    user.groups.add(organization.group)
    return Response({})


@extend_schema(
    description="Remove a user from an organization",
    parameters=[
        OpenApiParameter(
            name="pk",
            type=int,
            location=OpenApiParameter.PATH,
            description="Organization ID",
        ),
    ],
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.NONE},
)
@api_view(["POST"])
@permission_classes([OrganizationPermission])
@transaction.atomic
def remove_user(request, pk: int):
    user, organization = get_user_and_organization(request, pk)

    # Explicit object-level permission check
    permission = OrganizationPermission()
    if not permission.has_object_permission(request, None, organization):
        return HttpResponseForbidden("You do not have permission to modify this organization.")

    user.groups.remove(organization.group)
    return Response({})

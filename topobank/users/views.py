from allauth.utils import generate_unique_username
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response

from ..organizations.models import resolve_organization
from ..organizations.permissions import OrganizationPermission
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

        # Filter for name, username, or email
        if name is not None:
            qs = qs.filter(
                Q(name__icontains=name)
                | Q(username__icontains=name)
                | Q(email__icontains=name)
            )

        # Filter for organization
        if organization is not None:
            qs = qs.filter(groups__organization=organization)

        # Return query set with distinct to avoid duplicates from group joins
        return qs.distinct()

    def create(self, request, *args, **kwargs):
        data: dict = request.data
        if data.get("username"):
            username = data.pop("username")
        else:
            username = generate_unique_username([data.get("email"), data.get("name")])
        serializer = self.get_serializer(data={**data, "username": username})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=201)


def get_user_and_organization(request, pk):
    user = get_object_or_404(User, pk=pk)
    organization_url = request.data.get("organization")
    organization = resolve_organization(organization_url)
    return user, organization


@extend_schema(
    description="Add a user to an organization",
    parameters=[
        OpenApiParameter(
            name="pk",
            type=int,
            location=OpenApiParameter.PATH,
            description="User ID",
        ),
    ],
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.NONE},
)
@api_view(["POST"])
@permission_classes([UserPermission])
def add_organization(request, pk: int):
    user, organization = get_user_and_organization(request, pk)

    # Explicit object-level permission checks
    user_permission = UserPermission()
    if not user_permission.has_object_permission(request, None, user):
        return HttpResponseForbidden("You do not have permission to modify this user.")

    org_permission = OrganizationPermission()
    if not org_permission.has_object_permission(request, None, organization):
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
            description="User ID",
        ),
    ],
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.NONE},
)
@api_view(["POST"])
@permission_classes([UserPermission])
def remove_organization(request, pk: int):
    user, organization = get_user_and_organization(request, pk)

    # Explicit object-level permission checks
    user_permission = UserPermission()
    if not user_permission.has_object_permission(request, None, user):
        return HttpResponseForbidden("You do not have permission to modify this user.")

    org_permission = OrganizationPermission()
    if not org_permission.has_object_permission(request, None, organization):
        return HttpResponseForbidden("You do not have permission to modify this organization.")

    user.groups.remove(organization.group)
    return Response({})

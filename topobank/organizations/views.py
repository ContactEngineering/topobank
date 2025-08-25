from rest_framework import viewsets
from rest_framework.pagination import LimitOffsetPagination

from .models import Organization
from .permissions import OrganizationPermission
from .serializers import OrganizationSerializer


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSerializer
    pagination_class = LimitOffsetPagination
    permission_classes = [OrganizationPermission]

    def get_queryset(self):
        if self.request.user.is_staff:
            # Staff users can see all organizations
            return Organization.objects.all()
        elif self.request.user.is_authenticated:
            # Normal users can only see organizations they are member of
            return Organization.objects.filter(
                group__in=self.request.user.groups.all()
            ).distinct()
        return Organization.objects.none()

from rest_framework import viewsets
from rest_framework.pagination import LimitOffsetPagination

from .permissions import OrganizationPermission
from .serializers import OrganizationSerializer


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSerializer
    pagination_class = LimitOffsetPagination
    permission_classes = [OrganizationPermission]

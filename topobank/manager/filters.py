from django_filters import rest_framework as filters

from.models import Surface, Topography

class SurfaceFilterSet(filters.FilterSet):
    name = filters.CharFilter(lookup_expr='icontains')
    description = filters.CharFilter(lookup_expr='icontains')

    class Meta:
        model = Surface
        fields = ('name', 'description')

class TopographyFilterSet(filters.FilterSet):
    name = filters.CharFilter(lookup_expr='icontains')
    description = filters.CharFilter(lookup_expr='icontains')

    class Meta:
        model = Topography
        fields = ('name', 'description')



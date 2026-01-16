from django.db.models import Count
from django_filters.rest_framework import FilterSet, filters

from topobank.manager.models import Surface, Topography


class TopographyViewFilterSet(FilterSet):
    """
    FilterSet for Topography model.

    Filters:
    - surface: Filter by surface IDs (list)
    - tag: Filter by exact tag name
    - tag_startswith: Filter by tag name starting with substring
    """

    surface = filters.BaseInFilter(field_name="surface__id")
    tag = filters.CharFilter(method="filter_tag_iexact")
    tag_startswith = filters.CharFilter(method="filter_tag_istartswith")

    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    created_by = filters.CharFilter(field_name="created_by__name", lookup_expr="icontains")
    updated_by = filters.CharFilter(field_name="updated_by__name", lookup_expr="icontains")
    owned_by = filters.CharFilter(field_name="owned_by__name", lookup_expr="icontains")

    order = filters.OrderingFilter(
        fields=['created_at', 'updated_at']
    )

    class Meta:
        model = Topography
        fields = [
            "surface",
            "tag",
            "tag_startswith",
            "name",
            "created_by",
            "updated_by",
            "owned_by",
            "order",
        ]

    def filter_tag_iexact(self, queryset, name, value):
        """
        Filter by exact tag path (case-insensitive) and all child tags.

        Note:
        -----
        This filter will only return the exact tag and not its children.
        """
        # Tag path replaces spaces with hyphens
        path = value.replace(" ", "-")
        # Note: .distinct() is applied in the viewset's filter_queryset() method
        # when tag filters are detected to handle ManyToMany JOIN duplicates
        return queryset.filter(surface__tags__path__iexact=path)

    def filter_tag_istartswith(self, queryset, name, value):
        """
        Filter by tag path starting with substring (case-insensitive).
        """
        # Tag path replaces spaces with hyphens
        path = value.replace(" ", "-")
        return queryset.filter(
            surface__tags__path__istartswith=path
        )


class SurfaceViewFilterSet(FilterSet):
    """
    FilterSet for Surface model.

    Filters:
    - tag: Filter by exact tag name
    - tag_startswith: Filter by tag name starting with substring
    """

    tag = filters.CharFilter(method="filter_tag_iexact")
    tag_startswith = filters.CharFilter(method="filter_tag_istartswith")
    tag_contains = filters.CharFilter(method="filter_tag_contains")
    has_tags = filters.BooleanFilter(method="filter_has_tags")
    property = filters.CharFilter(field_name="properties__name", lookup_expr="istartswith", distinct=True)
    topography = filters.BaseInFilter(field_name="topography__id")

    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    created_by = filters.CharFilter(field_name="created_by__name", lookup_expr="icontains")
    updated_by = filters.CharFilter(field_name="updated_by__name", lookup_expr="icontains")
    owned_by = filters.CharFilter(field_name="owned_by__name", lookup_expr="icontains")

    order = filters.OrderingFilter(
        fields=['created_at', 'updated_at']
    )

    class Meta:
        model = Surface
        fields = [
            "tag",
            "tag_startswith",
            "tag_contains",
            "has_tags",
            "name",
            "property",
            "topography",
            "created_by",
            "owned_by",
            "updated_by",
            "order",
        ]

    def filter_tag_iexact(self, queryset, name, value):
        """
        Filter by exact tag path (case-insensitive) and all child tags.

        Note:
        -----
        This filter will only return the exact tag and not its children.
        """
        # Tag path replaces spaces with hyphens
        path = value.replace(" ", "-")
        return queryset.filter(tags__path__iexact=path)

    def filter_tag_istartswith(self, queryset, name, value):
        """
        Filter by tag path starting with substring (case-insensitive).
        """
        # Tag path replaces spaces with hyphens
        path = value.replace(" ", "-")
        return queryset.filter(
            tags__path__istartswith=path
        )

    def filter_tag_contains(self, queryset, name, value):
        """
        Filter by tag path containing substring (case-insensitive).
        """
        # Tag path replaces spaces with hyphens
        path = value.replace(" ", "-")
        return queryset.filter(
            tags__path__icontains=path
        )

    def filter_has_tags(self, queryset, name, value):
        """
        Filter surfaces that have (or do not have) any tags.
        """
        if value:
            return queryset.annotate(tag_count=Count('tags')).filter(tag_count__gt=0)
        else:
            return queryset.annotate(tag_count=Count('tags')).filter(tag_count=0)

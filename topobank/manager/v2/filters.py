from django.db.models import Count, Subquery
from django_filters.rest_framework import FilterSet, filters

from topobank.manager.models import Surface, Topography

"""
Note on Tag filtering performance:
--------------------------------------------
This is a deliberate pattern to avoid JOIN-related duplicate
rows while preserving the original queryset's structure.

The problem with filtering directly on the queryset:
If you did:
```
    return queryset.filter(surface__tags__path__iexact=path)
```
Django creates a JOIN between Topography → Surface → Tags.
If a surface has multiple tags, or if the relationship causes
row multiplication, you can get duplicate Topography rows in
the result.

To fix this you would need .distinct(), but on a complex queryset
with annotations/ordering that has downsides:
    1. It can be very expensive, especially on wide tables with
        many columns.
    2. It may conflict with existing ORDER BY clauses.
        (PostgreSQL requires ordered columns in SELECT DISTINCT)
    3. It operates on all columns, not just the primary key.

Why the subquery pattern works better:
```
    matching_ids = Topography.objects.filter(
        surface__tags__path__iexact=path
    ).values_list('id', flat=True).distinct()

    return queryset.filter(id__in=Subquery(matching_ids))
```
    1. The inner (32-34) query finds matching IDs with
        .distinct() on just the ID column (cheap).
    2. The outer (36) queryset.filter(id__in=...) preserves the
        original queryset's annotations, ordering, and structure.
    3. No row multiplication in the main query since you're
        filtering by primary key
    4. The database optimizer handles the subquery efficiently.
        (often as a semi-join)

In summary: The queryset passed in may already have annotations,
ordering, or other modifications. Filtering directly with a JOIN
could duplicate rows or break those modifications. The subquery
pattern safely narrows the results by ID without affecting the
queryset's structure.
"""


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
        Filter by exact Tag path (case-insensitive) and all child tags.

        Note:
        -----
        This filter will only return Topographies whos Surface is a direct
        child of the exact Tag. Topographies that belong to a Surface in a
        child tag are NOT included.
        """
        # Tag path replaces spaces with hyphens
        path = value.replace(" ", "-")

        # Refer to the docstring at the top of this file for explanation
        matching_ids = Topography.objects.filter(
            surface__tags__path__iexact=path
        ).values_list('id', flat=True).distinct()
        return queryset.filter(id__in=Subquery(matching_ids))

    def filter_tag_istartswith(self, queryset, name, value):
        """
        Filter by Tag path starting with substring (case-insensitive).

        Note:
        -----
        This filter will return Topographies whos Surface is a child of
        any Tag/ child of the Tag that starts with the given substring.
        """
        # Tag path replaces spaces with hyphens
        path = value.replace(" ", "-")

        # Refer to the docstring at the top of this file for explanation
        matching_ids = Topography.objects.filter(
            surface__tags__path__istartswith=path
        ).values_list('id', flat=True).distinct()
        return queryset.filter(id__in=Subquery(matching_ids))


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
        Filter by exact Tag path (case-insensitive) and all child Tags.

        Note:
        -----
        This filter will only return the Surfaces directly under this
        exact Tag. Surfaces under a child Tag are NOT included.
        """
        # Tag path replaces spaces with hyphens
        path = value.replace(" ", "-")

        # Refer to the docstring at the top of this file for explanation
        matching_ids = Surface.objects.filter(
            tags__path__iexact=path
        ).values_list('id', flat=True).distinct()
        return queryset.filter(id__in=Subquery(matching_ids))

    def filter_tag_istartswith(self, queryset, name, value):
        """
        Filter by Tag path starting with substring (case-insensitive).

        Note:
        -----
        This filter will return Surfaces under any Tag/ child of the Tag
        that starts with the given substring.
        """
        # Tag path replaces spaces with hyphens
        path = value.replace(" ", "-")

        # Refer to the docstring at the top of this file for explanation
        matching_ids = Surface.objects.filter(
            tags__path__istartswith=path
        ).values_list('id', flat=True).distinct()
        return queryset.filter(id__in=Subquery(matching_ids))

    def filter_tag_contains(self, queryset, name, value):
        """
        Filter by Tag path containing substring (case-insensitive).
        """
        # Tag path replaces spaces with hyphens
        path = value.replace(" ", "-")

        # Refer to the docstring at the top of this file for explanation
        matching_ids = Surface.objects.filter(
            tags__path__icontains=path
        ).values_list('id', flat=True).distinct()
        return queryset.filter(id__in=Subquery(matching_ids))

    def filter_has_tags(self, queryset, name, value):
        """
        Filter Surfaces that have (or do not have) any Tags.
        """
        if value:
            return queryset.annotate(tag_count=Count('tags')).filter(tag_count__gt=0)
        else:
            return queryset.annotate(tag_count=Count('tags')).filter(tag_count=0)

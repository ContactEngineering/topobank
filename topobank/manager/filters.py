from django_filters import rest_framework as filters
from django.db.models import Q

from .models import Surface, TagModel

SHARING_STATUS_CHOICES = [
    ('own', 'Only own surfaces'),
    ('shared', 'Only surfaces shared with you')
]


class SurfaceFilter(filters.FilterSet):

    search = filters.CharFilter(label="Search term", method='filter_by_search_term')
    category = filters.ChoiceFilter(choices=Surface.CATEGORY_CHOICES)
    sharing_status = filters.ChoiceFilter(label="Sharing status", choices=SHARING_STATUS_CHOICES,
                                          method='filter_by_sharing_status')

    class Meta:
        model = Surface
        fields = []

    def filter_by_search_term(self, queryset, name, value):
        # A surface should also be in the result if a topography
        # contains the search term in name or description or in tags
        queryset = queryset.filter(name__icontains=value)\
                   | queryset.filter(description__icontains=value) \
                   | queryset.filter(tags__name__icontains=value) \
                   | queryset.filter(topography__name__icontains=value)\
                   | queryset.filter(topography__description__icontains=value)\
                   | queryset.filter(topography__tags__name__icontains=value)

        return queryset.distinct()

    def filter_by_sharing_status(self, queryset, name, value):
        if value == 'own':
            queryset = queryset.filter(creator=self.request.user)
        elif value == 'shared':
            queryset = queryset.filter(~Q(creator=self.request.user))

        return queryset


class TagModelFilter(filters.FilterSet):

    search = filters.CharFilter(label="Search term", method='filter_by_search_term')
    category = filters.ChoiceFilter(choices=Surface.CATEGORY_CHOICES, method='filter_by_category')
    sharing_status = filters.ChoiceFilter(label="Sharing status", choices=SHARING_STATUS_CHOICES,
                                          method='filter_by_sharing_status')

    class Meta:
        model = TagModel
        fields = []

    def filter_by_search_term(self, queryset, name, value):

        queryset = queryset.filter(name__icontains=value)

        return queryset.distinct()

    def filter_by_category(self, queryset, name, value):
        return queryset

    def filter_by_sharing_status(self, queryset, name, value):
        # TODO How to filter for sharing status?
        if value == 'own':
            queryset = queryset.filter(creator=self.request.user)
        elif value == 'shared':
            queryset = queryset.filter(~Q(creator=self.request.user))

        return queryset



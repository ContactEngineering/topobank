from django.db.models import Q
from rest_framework.filters import BaseFilterBackend

from .utils import get_category, get_search_term, get_sharing_status


class SurfaceFilter(BaseFilterBackend):
    """
    Filters surfaces based on current request.
    """
    def filter_queryset(self, request, queryset, view):
        user = request.user

        #
        # Filter by category and sharing status
        #
        category = get_category(request)
        if category:
            queryset = queryset.filter(category=category)

        sharing_status = get_sharing_status(request)
        if sharing_status == 'own':
            queryset = queryset.filter(creator=user)
        elif sharing_status == 'shared':
            queryset = queryset.filter(~Q(creator=user))

        #
        # Filter by search term
        #
        search_term = get_search_term(request)
        if search_term:
            #
            # find all topographies which should be at top level
            #
            queryset = queryset.filter(Q(name__icontains=search_term) |
                           Q(description__icontains=search_term) |
                           Q(tags__name__icontains=search_term) |
                           Q(topography__name__icontains=search_term) |
                           Q(topography__description__icontains=search_term) |
                           Q(topography__tags__name__icontains=search_term)).distinct()
        return queryset


class TagFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):



        pass

from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db.models import Q, Subquery, TextField, Value
from django.db.models.functions import Replace
from rest_framework.exceptions import ParseError, PermissionDenied

from topobank.manager.models import Surface

ORDER_BY_FILTER_CHOICES = {"name": "name", "date": "-created_at"}
SHARING_STATUS_FILTER_CHOICES = set(["all", "own", "others", "published"])


# v1 filter
def filter_by_search_term(
    request,
    qs,
    search_fields=[
        "description",
        "name",
        "created_by__name",
        "tag_names_for_search",
        "topography_name_for_search",
        "topography__description",
        "topography_tag_names_for_search",
        "topography__created_by__name",
    ],
):
    """Filter queryset for a given search term.

    Parameters
    ----------
    qs : QuerySet
        QuerySet which should be additionally filtered by a search term.
    search_term: str
        Search term entered by the user. Can be an expression.
        See https://docs.djangoproject.com/en/3.2/ref/contrib/postgres/search/
        for details.
    search_fields: list of str
        ORM expressions which refer to search fields, e.g. "description"
        or "topography__description" for the description field of a child object

    Returns
    -------
    Filtered query set.
    """
    #
    # search specific fields of all surfaces in a 'websearch' manner:
    # combine phrases by "AND", allow expressions and quotes
    #
    # See https://docs.djangoproject.com/en/3.2/ref/contrib/postgres/search/#full-text-search
    # for details.
    #
    # We introduce an extra field for search in tag names where the tag names
    # are changed so that the tokenizer splits the names into multiple words
    search_term = request.GET.get("search", default="")
    if not search_term:
        return qs
    qs = (
        qs.annotate(
            tag_names_for_search=Replace(
                Replace("tags__name", Value("."), Value(" ")),  # replace . with space
                Value("/"),
                Value(" "),
            ),  # replace / with space
            topography_tag_names_for_search=Replace(  # same for the topographies
                Replace("topography__tags__name", Value("."), Value(" ")),
                Value("/"),
                Value(" "),
            ),
            topography_name_for_search=Replace(
                "topography__name", Value("."), Value(" "), output_field=TextField()
            ),
            # often there are filenames
        )
        .distinct("id")
        .order_by("id")
    )
    qs = (
        qs.annotate(search=SearchVector(*search_fields, config="english"))
        .filter(
            search=SearchQuery(search_term, config="english", search_type="websearch")
            # search__icontains=search_term  # alternative, which finds substrings but does not allow for expressions
        )
        .distinct("id")
        .order_by("id")
    )
    return qs


# v1 filter
def filter_by_sharing_status(request, qs):
    sharing_status = request.GET.get("sharing_status", default="all")
    if sharing_status not in SHARING_STATUS_FILTER_CHOICES:
        raise ParseError(f"Cannot filter for sharing status '{sharing_status}'.")
    if sharing_status == "own":
        qs = qs.filter(created_by=request.user)
        if hasattr(Surface, "publication"):
            qs = qs.exclude(
                publication__isnull=False
            )  # exclude published and own surfaces
    elif sharing_status == "others":
        qs = qs.exclude(created_by=request.user)
        if hasattr(Surface, "publication"):
            qs = qs.exclude(
                publication__isnull=False
            )  # exclude published and own surfaces
    elif sharing_status == "published":
        if hasattr(Surface, "publication"):
            qs = qs.filter(publication__isnull=False)
        else:
            qs = Surface.objects.none()
    elif sharing_status == "all":
        pass
    else:
        raise PermissionDenied(f"Cannot filter for sharing status '{sharing_status}'.")
    return qs


# v1 filter
def filter_by_tag(request, qs):
    tag = request.query_params.get("tag", None)
    tag_startswith = request.query_params.get("tag_startswith", None)
    if tag is not None:
        if tag_startswith is not None:
            raise ParseError(
                "Please specify either `tag` or `tag_startswith`, not both."
            )
        if tag:
            qs = qs.filter(tags__name=tag)
        else:
            qs = qs.filter(tags=None)
    elif tag_startswith is not None:
        if tag_startswith:
            qs = (
                qs.filter(
                    Q(tags__name=tag_startswith)
                    | Q(tags__name__startswith=tag_startswith.rstrip("/") + "/")
                )
                .order_by("id")
                .distinct("id")
            )
        else:
            raise ParseError("`tag_startswith` cannot be empty.")
    return qs


# v1 filter
def order_results(request, qs):
    order_by = request.GET.get("order_by", default="date")
    if order_by not in ORDER_BY_FILTER_CHOICES:
        raise ParseError(f"Cannot order by '{order_by}'.")
    qs = Surface.objects.filter(pk__in=Subquery(qs.values("pk"))).order_by(
        ORDER_BY_FILTER_CHOICES[order_by]
    )
    return qs


# v1 filter
def filter_surfaces(request, qs):
    """Return queryset with surfaces matching all filter criteria.

    Surfaces should be
    - readable by the current user
    - filtered by sharing status
    - filtered by search expression, if given

    Parameters
    ----------
    request
        Request instance

    Returns
    -------
        Filtered queryset of surfaces
    """
    filters = [
        filter_by_tag,
        filter_by_sharing_status,
        filter_by_search_term,
        order_results,
    ]

    for filter in filters:
        qs = filter(request, qs)

    return qs

from datetime import date

from django.conf import settings
from django.db import transaction
from django.db.models import F
from trackstats.models import Period, StatisticByDate, StatisticByDateAndObject


def register_metrics():
    """Registers all metrics used with package 'trackstats'.

    Make sure this is called before using metrics.

    Returns
    -------
        None
    """

    from trackstats.models import Domain, Metric

    Domain.objects.REQUESTS = Domain.objects.register(ref="requests", name="Requests")
    Metric.objects.TOTAL_REQUEST_COUNT = Metric.objects.register(
        domain=Domain.objects.REQUESTS,
        ref="total_request_count",
        name="Total number of requests of any kind",
    )

    Domain.objects.VIEWS = Domain.objects.register(ref="views", name="Views")
    Metric.objects.SEARCH_VIEW_COUNT = Metric.objects.register(
        domain=Domain.objects.VIEWS,
        ref="search_view_count",
        name="Number of views for Search page",
    )
    Metric.objects.ANALYSES_RESULTS_VIEW_COUNT = Metric.objects.register(
        domain=Domain.objects.VIEWS,
        ref="analyses_results_view_count",
        name="Number of views for Analyses results",
    )
    Metric.objects.SURFACE_VIEW_COUNT = Metric.objects.register(
        domain=Domain.objects.VIEWS,
        ref="surface_view_count",
        name="Number of views for surfaces",
    )
    Metric.objects.PUBLICATION_VIEW_COUNT = Metric.objects.register(
        domain=Domain.objects.VIEWS,
        ref="publication_view_count",
        name="Number of requests for publication URLs",
    )

    Domain.objects.DOWNLOADS = Domain.objects.register(
        ref="downloads", name="Downloads"
    )
    Metric.objects.SURFACE_DOWNLOAD_COUNT = Metric.objects.register(
        domain=Domain.objects.DOWNLOADS,
        ref="surface_download_count",
        name="Number of downloads of surfaces",
    )

    Domain.objects.USERS = Domain.objects.register(ref="users", name="Users")
    Metric.objects.USERS_LOGIN_COUNT = Metric.objects.register(
        domain=Domain.objects.USERS,
        ref="login_count",
        name="Number of users having logged in",
    )

    Domain.objects.PROFILE = Domain.objects.register(ref="profile", name="Profile")
    Metric.objects.TOTAL_ANALYSIS_CPU_MS = Metric.objects.register(
        domain=Domain.objects.PROFILE,
        ref="total_analysis_cpu_ms",
        name="Total number of milliseconds spent for analysis computation",
    )

    Domain.objects.OBJECTS = Domain.objects.register(ref="objects", name="Objects")
    Metric.objects.USER_COUNT = Metric.objects.register(
        domain=Domain.objects.OBJECTS,
        ref="total_number_users",
        name="Total number of registered users",
    )
    Metric.objects.SURFACE_COUNT = Metric.objects.register(
        domain=Domain.objects.OBJECTS,
        ref="total_number_surfaces",
        name="Total number of surfaces",
    )
    Metric.objects.TOPOGRAPHY_COUNT = Metric.objects.register(
        domain=Domain.objects.OBJECTS,
        ref="total_number_topographies",
        name="Total number of topographies",
    )
    Metric.objects.ANALYSIS_COUNT = Metric.objects.register(
        domain=Domain.objects.OBJECTS,
        ref="total_number_analyses",
        name="Total number of analyses",
    )


@transaction.atomic
def increase_statistics_by_date(metric, period=Period.DAY, increment=1):
    """Increase statistics by date in database using the current date.

    Initializes statistics by date to given increment, if it does not
    exist.

    Parameters
    ----------
    metric: trackstats.models.Metric object

    period: trackstats.models.Period object, optional
        Examples: Period.LIFETIME, Period.DAY
        Defaults to Period.DAY, i.e. store
        incremental values on a daily basis.

    increment: int, optional
        How big the the increment, default to 1.


    Returns
    -------
        None
    """
    if not settings.ENABLE_USAGE_STATS:
        return

    today = date.today()

    if StatisticByDate.objects.filter(
        metric=metric, period=period, date=today
    ).exists():
        # we need this if-clause, because F() expressions
        # only works on updates but not on inserts
        StatisticByDate.objects.record(
            date=today, metric=metric, value=F("value") + increment, period=period
        )
    else:
        StatisticByDate.objects.record(
            date=today, metric=metric, value=increment, period=period
        )


@transaction.atomic
def increase_statistics_by_date_and_object(metric, obj, period=Period.DAY, increment=1):
    """Increase statistics by date in database using the current date.

    Initializes statistics by date to given increment, if it does not
    exist.

    Parameters
    ----------
    metric: trackstats.models.Metric object

    obj: any class for which a contenttype exists, e.g. Topography
        Some object for which this metric should be increased.
    period: trackstats.models.Period object, optional
        Examples: Period.LIFETIME, Period.DAY
        Defaults to Period.DAY, i.e. store
        incremental values on a daily basis.

    increment: int, optional
        How big the the increment, default to 1.


    Returns
    -------
        None
    """
    if not settings.ENABLE_USAGE_STATS:
        return

    today = date.today()

    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(obj)

    at_least_one_entry_exists = StatisticByDateAndObject.objects.filter(
        metric=metric, period=period, date=today, object_id=obj.id, object_type_id=ct.id
    ).exists()

    if at_least_one_entry_exists:
        # we need this if-clause, because F() expressions
        # only works on updates but not on inserts
        StatisticByDateAndObject.objects.record(
            date=today,
            metric=metric,
            object=obj,
            value=F("value") + increment,
            period=period,
        )
    else:
        StatisticByDateAndObject.objects.record(
            date=today, metric=metric, object=obj, value=increment, period=period
        )


def current_statistics(user=None):
    """Return some statistics about managed data.

    These values are calculated from current counts
    of database objects.

    Parameters
    ----------
        user: User instance
            If given, the statistics is only related to the surfaces of a given user
            (as creator)

    Returns
    -------
        dict with keys

        - num_surfaces_excluding_publications
        - num_topographies_excluding_publications
        - num_analyses_excluding_publications
    """
    from topobank.analysis.models import WorkflowResult
    from topobank.manager.models import Surface, Topography

    if hasattr(Surface, "publication"):
        if user:
            unpublished_surfaces = Surface.objects.filter(
                creator=user, publication__isnull=True, deletion_time__isnull=True
            )
        else:
            unpublished_surfaces = Surface.objects.filter(
                publication__isnull=True, deletion_time__isnull=True
            )
    else:
        if user:
            unpublished_surfaces = Surface.objects.filter(
                creator=user, deletion_time__isnull=True
            )
        else:
            unpublished_surfaces = Surface.objects.filter(deletion_time__isnull=True)
    unpublished_topographies = Topography.objects.filter(
        surface__in=unpublished_surfaces, deletion_time__isnull=True
    )
    unpublished_analyses = WorkflowResult.objects.filter(
        subject_dispatch__topography__in=unpublished_topographies
    )

    return dict(
        num_surfaces_excluding_publications=unpublished_surfaces.count(),
        num_topographies_excluding_publications=unpublished_topographies.count(),
        num_analyses_excluding_publications=unpublished_analyses.count(),
    )

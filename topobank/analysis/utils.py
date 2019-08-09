from topobank.analysis.models import Analysis
from django.db.models import OuterRef, Subquery

def get_latest_analyses(function_id, topography_ids):
    """Get latest analyses for given function and topographies.

    :param function_id: id of AnalysisFunction instance
    :param topography_ids: iterable of ids of Topography instances
    :return: Queryset of analyses

    The returned queryset is comprised of only the latest analyses,
    so for each topography id there should be at most one result.
    Only analyses for the given function are returned.
    """

    sq_analyses = Analysis.objects \
                .filter(topography_id__in=topography_ids,
                        function_id=function_id) \
                .filter(topography=OuterRef('topography'), function=OuterRef('function'),
                        kwargs=OuterRef('kwargs')) \
                .order_by('-start_time')

    # Use this subquery for finding only latest analyses for each (topography, kwargs) group
    analyses = Analysis.objects \
        .filter(pk=Subquery(sq_analyses.values('pk')[:1])) \
        .order_by('topography__name')

    # thanks to minkwe for the contribution at https://gist.github.com/ryanpitts/1304725
    # maybe be better solved with PostGreSQL and Window functions

    return analyses

def mangle_sheet_name(s: str) -> str:
    """Return a string suitable for a sheet name in Excel/Libre Office.

    :param s: sheet name
    :return: string which should be suitable for sheet names
    """

    replacements = {
        ':': '',
        '[': '(',
        ']': ')',
        '*': '',
        '?': '',
        "'": '"',
        "\\": ""
    }

    for x, y in replacements.items():
        s = s.replace(x, y)

    return s

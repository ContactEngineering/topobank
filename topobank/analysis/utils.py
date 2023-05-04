import inspect
import logging
import math
from collections import OrderedDict

from bokeh import palettes as palettes
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q

from .models import Analysis, AnalysisFunction

_log = logging.getLogger(__name__)


# This used only in the `trigger_analyses` management command
def renew_analyses_for_subject(subject):
    """Renew all analyses for the given subject.

    At first all existing analyses for the given subject
    will be deleted. Only analyses for the default parameters
    will be automatically generated at the moment.

    Implementation Note:

    This method cannot be easily used in a post_save signal,
    because the pre_delete signal deletes the datafile and
    this also then triggers "renew_analyses".
    """
    analysis_funcs = AnalysisFunction.objects.all()

    # collect users which are allowed to use these analyses by default
    users_for_subject = subject.get_users_with_perms()

    def submit_all(subj=subject):
        """Trigger analyses for this subject for all available analyses functions."""
        _log.info(f"Deleting all analyses for {subj.get_content_type().name} {subj.id}...")
        subj.analyses.all().delete()
        _log.info(f"Triggering analyses for {subj.get_content_type().name} {subj.id} and all analysis functions...")
        for af in analysis_funcs:
            subject_type = subj.get_content_type()
            if af.is_implemented_for_type(subject_type):
                # filter also for users who are allowed to use the function
                users = [u for u in users_for_subject if af.get_implementation(subject_type).is_available_for_user(u)]
                try:
                    submit_analysis(users, af, subject=subj)
                except Exception as err:
                    _log.error(f"Cannot submit analysis for function '{af.name}' and subject '{subj}' "
                               f"({subj.get_content_type().name} {subj.id}). Reason: {str(err)}")

    transaction.on_commit(lambda: submit_all(subject))


def renew_analysis(analysis, use_default_kwargs=False):
    """Delete existing analysis and recreate and submit with same arguments and users.

    Parameters
    ----------
    analysis: Analysis
        Analysis instance to be renewed.
    use_default_kwargs: boolean
        If True, use default arguments of the corresponding analysis function implementation.
        If False (default), use the keyword arguments of the given analysis.

    Returns
    -------
    New analysis object.
    """
    users = analysis.users.all()
    func = analysis.function

    subject_type = ContentType.objects.get_for_model(analysis.subject)

    if use_default_kwargs:
        pyfunc_kwargs = func.get_default_kwargs(subject_type=subject_type)
    else:
        pyfunc_kwargs = analysis.kwargs

    _log.info(f"Renewing analysis {analysis.id} for {len(users)} users, function {func.name}, "
              f"subject type {subject_type}, subject id {analysis.subject.id} .. "
              f"kwargs: {pyfunc_kwargs}")
    analysis.delete()
    return submit_analysis(users, func, subject=analysis.subject,
                           pyfunc_kwargs=pyfunc_kwargs)


def submit_analysis(users, analysis_func, subject, pyfunc_kwargs=None):
    """Create an analysis entry and submit a task to the task queue.

    :param users: sequence of User instances; users which should see the analysis
    :param subject: instance which will be subject of the analysis (first argument of analysis function)
    :param analysis_func: AnalysisFunc instance
    :param pyfunc_kwargs: kwargs for function which should be saved to database
    :returns: Analysis object

    If None is given for 'pyfunc_kwargs', the default arguments for the given analysis function are used.
    The default arguments are the ones used in the function implementation (python function).

    Typical instances as subjects are topographies or surfaces.
    """
    subject_type = ContentType.objects.get_for_model(subject)

    #
    # create entry in Analysis table
    #
    if pyfunc_kwargs is None:
        # Instead of an empty dict, we explicitly store the current default arguments of the analysis function
        pyfunc_kwargs = analysis_func.get_default_kwargs(subject_type=subject_type)

    analysis = Analysis.objects.create(
        subject=subject,
        function=analysis_func,
        task_state=Analysis.PENDING,
        kwargs=pyfunc_kwargs)

    analysis.users.set(users)

    #
    # delete all completed old analyses for same function and subject and arguments
    # There should be only one analysis per function, subject and arguments
    #
    Analysis.objects.filter(
        ~Q(id=analysis.id)
        & Q(subject_type=subject_type)
        & Q(subject_id=subject.id)
        & Q(function=analysis_func)
        & Q(kwargs=pyfunc_kwargs)
        & Q(task_state__in=[Analysis.FAILURE, Analysis.SUCCESS])).delete()

    #
    # TODO delete all started old analyses, where the task does not exist any more
    #
    # maybe_aborted_analyses = Analysis.objects.filter(
    #    ~Q(id=analysis.id)
    #    & Q(topography=topography)
    #    & Q(function=analysis_func)
    #    & Q(task_state__in=[Analysis.STARTED]))
    # How to find out if task is still running?
    #
    # for a in maybe_aborted_analyses:
    #    result = app.AsyncResult(a.task_id)

    # Send task to the queue if the analysis has been created
    from topobank.taskapp.tasks import perform_analysis
    transaction.on_commit(lambda: perform_analysis.delay(analysis.id))

    return analysis


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


def round_to_significant_digits(x, num_dig_digits):
    """Round given number to given number of significant digits

    Parameters
    ----------
    x: flost
        Number to be rounded
    num_dig_digits: int
        Number of significant digits


    Returns
    -------
    Rounded number.

    For NaN, NaN is returned.
    """
    if math.isnan(x):
        return x
    try:
        return round(x, num_dig_digits - int(math.floor(math.log10(abs(x)))) - 1)
    except ValueError:
        return x


def filter_and_order_analyses(analyses):
    """Order analyses such that surface analyses are coming last (plotted on top).

    The analyses are filtered that that surface analyses
    are only included if there are more than 1 measurement.

    Parameters
    ----------
    analyses: list of Analysis instances
        Analyses to be filtered and sorted.

    Returns
    -------
    Ordered list of analyses. Analyses for measurements
    are listed directly after corresponding surface.
    """
    from topobank.manager.models import Surface, SurfaceCollection, Topography

    surface_ct = ContentType.objects.get_for_model(Surface)
    surfacecollection_ct = ContentType.objects.get_for_model(SurfaceCollection)
    topography_ct = ContentType.objects.get_for_model(Topography)

    sorted_analyses = []

    #
    # Order analyses by surface
    # such that for each surface the analyses are ordered by subject id
    #
    analysis_groups = OrderedDict()  # always the same order of surfaces for same list of subjects
    for topography_analysis in sorted([analysis for analysis in analyses if analysis.subject_type == topography_ct],
                                      key=lambda analysis: analysis.subject_id):
        surface = topography_analysis.subject.surface
        if not surface in analysis_groups:
            analysis_groups[surface] = []
        analysis_groups[surface].append(topography_analysis)

    #
    # Process groups and collect analyses which are implicitly sorted
    #
    analyses_of_surfaces = sorted([a for a in analyses if a.subject_type == surface_ct],
                                  key=lambda a: a.subject_id)
    surfaces_of_surface_analyses = [a.subject for a in analyses_of_surfaces]
    for surface, topography_analyses in analysis_groups.items():
        try:
            # Is there an analysis for the corresponding surface?
            surface_analysis_index = surfaces_of_surface_analyses.index(surface)
            surface_analysis = analyses_of_surfaces[surface_analysis_index]
            if surface.num_topographies() > 1:
                # only show average for surface if more than one topography
                sorted_analyses.append(surface_analysis)
                surface_analysis_index = len(sorted_analyses) - 1  # last one
        except ValueError:
            # No analysis given for surface, so skip
            surface_analysis_index = None

        #
        # Add topography analyses whether there was a surface analysis or not
        # This will result in same order of topography analysis, no matter whether there was a surface analysis
        #
        if surface_analysis_index is None:
            sorted_analyses.extend(topography_analyses)
        else:
            # Insert corresponding topography analyses after surface analyses
            sorted_analyses = sorted_analyses[:surface_analysis_index + 1] + topography_analyses \
                              + sorted_analyses[surface_analysis_index + 1:]

    #
    # Finally add analyses for surface collections, if any
    #
    for collection_analysis in sorted([a for a in analyses if a.subject_type == surfacecollection_ct],
                                      key=lambda a: a.subject_id):
        sorted_analyses.append(collection_analysis)

    return sorted_analyses


def palette_for_topographies(nb_topographies):
    """Return a palette to distinguish topographies by color in a plot.

    Parameters
    ----------
    nb_topographies: int
        Number of topographies
    """
    if nb_topographies <= 10:
        topography_colors = palettes.Category10_10
    else:
        topography_colors = [palettes.Plasma256[k * 256 // nb_topographies] for k in range(nb_topographies)]
        # we don't want to have yellow as first color
        topography_colors = topography_colors[nb_topographies // 2:] + topography_colors[:nb_topographies // 2]
    return topography_colors

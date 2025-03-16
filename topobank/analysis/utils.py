import logging
from collections import OrderedDict

from ..manager.models import Surface

_log = logging.getLogger(__name__)


def filter_and_order_analyses(analyses):
    """Order analyses such that surface analyses are coming last (plotted on top).

    The analyses are filtered such that surface analyses
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
    sorted_analyses = []

    #
    # Order analyses by surface
    # such that for each surface the analyses are ordered by subject id
    #
    analysis_groups = (
        OrderedDict()
    )  # always the same order of surfaces for same list of subjects
    for topography_analysis in sorted(
        [a for a in analyses if a.subject_dispatch.topography is not None],
        key=lambda a: a.subject_dispatch.topography_id,
    ):
        surface = topography_analysis.subject_dispatch.topography.surface
        if surface not in analysis_groups:
            analysis_groups[surface] = []
        analysis_groups[surface].append(topography_analysis)

    #
    # Process groups and collect analyses which are implicitly sorted
    #
    analyses_of_surfaces = sorted(
        [a for a in analyses if a.subject_dispatch.surface is not None],
        key=lambda a: a.subject_dispatch.surface_id,
    )
    surfaces_of_surface_analyses = [
        a.subject_dispatch.surface for a in analyses_of_surfaces
    ]
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
            sorted_analyses = (
                sorted_analyses[: surface_analysis_index + 1]
                + topography_analyses
                + sorted_analyses[surface_analysis_index + 1 :]
            )

    #
    # Finally add analyses for surface collections, if any
    #
    for tag_analysis in sorted(
        [a for a in analyses if a.subject_dispatch.tag is not None],
        key=lambda a: a.subject_dispatch.tag_id,
    ):
        sorted_analyses.append(tag_analysis)

    return sorted_analyses


def find_children(subjects):
    """
    Find all children for listed subjects. For example, a Topography is a child
    of a Surface.

    Parameters
    ----------
    subjects : list of Topography or Surface
        List of subjects.

    Returns
    -------
    List of Topography or Surface
        List of subjects, updated with children.
    """
    if subjects is None:
        return None

    additional_subjects = []
    for subject in subjects:
        if isinstance(subject, Surface):
            additional_subjects += list(subject.topography_set.all())
    return list(set(subjects + additional_subjects))

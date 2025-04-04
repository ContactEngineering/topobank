import logging
from collections import defaultdict

import pydantic
from django.conf import settings
from django.db.models import Case, F, Max, Sum, Value, When
from django.http import HttpResponseBadRequest
from pint import DimensionalityError, UndefinedUnitError, UnitRegistry
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import api_view
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from trackstats.models import Metric

from ...files.serializers import ManifestSerializer
from ...manager.models import Surface
from ...manager.utils import demangle_content_type
from ...usage_stats.utils import increase_statistics_by_date_and_object
from ..models import Analysis, AnalysisFunction, Configuration
from ..permissions import AnalysisFunctionPermissions
from ..serializers import ConfigurationSerializer, ResultSerializer, WorkflowSerializer
from ..utils import filter_and_order_analyses
from .controller import AnalysisController

_log = logging.getLogger(__name__)

MAX_NUM_POINTS_FOR_SYMBOLS = (
    10000  # Don't show symbols if more than number of data points total
)
LINEWIDTH_FOR_SURFACE_AVERAGE = 4


class ConfigurationView(viewsets.GenericViewSet, mixins.RetrieveModelMixin):
    queryset = Configuration.objects.prefetch_related("versions")
    serializer_class = ConfigurationSerializer


class WorkflowView(
    viewsets.GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin
):
    lookup_field = "name"
    lookup_value_regex = "[a-z0-9._-]+"
    serializer_class = WorkflowSerializer
    permission_classes = [AnalysisFunctionPermissions]

    def get_queryset(self):
        # We need to filter the queryset to exclude functions in the list view
        user = self.request.user
        subject_type = self.request.query_params.get("subject_type", None)
        if subject_type is None:
            ids = [
                f.id for f in AnalysisFunction.objects.all() if f.has_permission(user)
            ]
        else:
            subject_class = demangle_content_type(subject_type)
            ids = [
                f.id
                for f in AnalysisFunction.objects.all()
                if f.has_permission(user)
                and f.implementation.has_implementation(subject_class.model_class())
            ]
        return AnalysisFunction.objects.filter(pk__in=ids)


class ResultView(
    viewsets.GenericViewSet, mixins.RetrieveModelMixin, mixins.DestroyModelMixin
):
    """Retrieve status of analysis (GET) and renew analysis (PUT)"""

    queryset = Analysis.objects.select_related(
        "function",
        "subject_dispatch__tag",
        "subject_dispatch__topography",
        "subject_dispatch__surface",
    ).order_by("-start_time")
    serializer_class = ResultSerializer
    pagination_class = LimitOffsetPagination

    def list(self, request, *args, **kwargs):
        try:
            controller = AnalysisController.from_request(request, **kwargs)
        except ValueError as err:
            return HttpResponseBadRequest(reason=str(err))

        #
        # Trigger missing analyses
        #
        try:
            controller.trigger_missing_analyses()
        except pydantic.ValidationError:
            # The kwargs that were provided do not match the function
            return HttpResponseBadRequest(
                "Error validating kwargs for analysis function"
            )

        #
        # Get context from controller and return
        #
        context = controller.get_context(request=request)

        return Response(context)

    def update(self, request, *args, **kwargs):
        """Renew existing analysis (PUT)."""
        analysis = self.get_object()
        analysis.authorize_user(request.user)
        if analysis.subject:
            new_analysis = analysis.submit_again()
            serializer = self.get_serializer(new_analysis)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return Response(
                {"message": "Cannot renew named analysis"},
                status=status.HTTP_403_FORBIDDEN,
            )


@api_view(["GET"])
def dependencies(request, workflow_id):
    analysis = get_object_or_404(Analysis, pk=workflow_id)
    analysis.authorize_user(request.user)
    dependencies = {}
    for name, id in analysis.dependencies.items():
        try:
            dependencies[name] = Analysis.objects.get(pk=id).get_absolute_url(request)
        except Analysis.DoesNotExist:
            dependencies[name] = None
    return Response(dependencies)


@api_view(["GET"])
def pending(request):
    queryset = Analysis.objects.for_user(request.user).filter(
        task_state__in=[Analysis.PENDING, Analysis.STARTED]
    )
    return Response(
        ResultSerializer(queryset, many=True, context={"request": request}).data
    )


@api_view(["GET"])
def named_result(request):
    queryset = Analysis.objects.for_user(request.user)
    name = request.query_params.get("name", None)
    if name is None:
        queryset = queryset.filter(name__isnull=False)
    else:
        queryset = queryset.filter(name__icontains=name)
    return Response(
        ResultSerializer(
            queryset.order_by("-start_time"), many=True, context={"request": request}
        ).data
    )


@api_view(["GET"])
def series_card_view(request, **kwargs):
    controller = AnalysisController.from_request(request, **kwargs)

    #
    # for statistics, count views per function
    #
    increase_statistics_by_date_and_object(
        Metric.objects.ANALYSES_RESULTS_VIEW_COUNT, obj=controller.workflow
    )

    #
    # Trigger missing analyses
    #
    controller.trigger_missing_analyses()

    #
    # Filter only successful ones
    #
    analyses_success = controller.get(task_states=["su"])

    #
    # order analyses such that surface analyses are coming last (plotted on top)
    #
    analyses_success_list = filter_and_order_analyses(analyses_success)
    data_sources_dict = []

    # Special case: It can happen that there is one surface with a successful analysis
    # but the only measurement's analysis has no success. In this case there is also
    # no successful analysis to display because the surface has only one measurement.

    context = controller.get_context(request=request)

    plot_configuration = {"title": controller.workflow.display_name}

    nb_analyses_success = len(analyses_success_list)
    if nb_analyses_success == 0:
        #
        # Prepare plot, controls, and table with special values..
        #
        plot_configuration["dataSources"] = []
        plot_configuration["categories"] = [
            {
                "title": "Averages / Measurements",
                "key": "subjectName",
            },
            {
                "title": "Data Series",
                "key": "seriesName",
            },
        ]
        context["plotConfiguration"] = plot_configuration
        return Response(context)

    #
    # Extract subject names for display
    #
    subject_names = (
        []
    )  # will be shown under category with key "subject_name" (see plot.js)
    has_at_least_one_surface_subject = False
    for a in analyses_success_list:
        s = a.subject
        subject_name = s.label.replace("'", "&apos;")
        if isinstance(s, Surface):
            subject_name = f"Average of »{subject_name}«"
            has_at_least_one_surface_subject = True
        subject_names.append(subject_name)

    #
    # Use first analysis to determine some properties for the whole plot
    #
    first_analysis_result = analyses_success_list[0].result
    xunit = first_analysis_result["xunit"] if "xunit" in first_analysis_result else "m"
    yunit = first_analysis_result["yunit"] if "yunit" in first_analysis_result else "m"

    ureg = (
        UnitRegistry()
    )  # for unit conversion for each analysis individually, see below

    #
    # Determine axes labels
    #
    x_axis_label = first_analysis_result["xlabel"]
    if xunit is not None:
        x_axis_label += f" ({xunit})"
    y_axis_label = first_analysis_result["ylabel"]
    if yunit is not None:
        y_axis_label += f" ({yunit})"

    #
    # Context information for the figure
    #
    def _get_axis_type(key):
        return first_analysis_result.get(key) or "linear"

    plot_configuration.update(
        {
            "xAxisLabel": x_axis_label,
            "yAxisLabel": y_axis_label,
            "xAxisType": _get_axis_type("xscale"),
            "yAxisType": _get_axis_type("yscale"),
            "outputBackend": settings.BOKEH_OUTPUT_BACKEND,
        }
    )

    #
    # First traversal: find all available series names and sort them
    #
    # Also collect number of topographies and surfaces
    #
    series_names = set()
    nb_tags = 0  # Total number of tags shown
    nb_surfaces = 0  # Total number of averages/surfaces shown
    nb_topographies = 0  # Total number of topography results shown
    nb_others = 0  # Total number of results for other kinds of subject types

    for analysis in analyses_success_list:
        #
        # handle task state
        #
        if analysis.task_state != analysis.SUCCESS:
            continue  # should not happen if only called with successful analyses

        series_metadata = analysis.result_metadata.get("series", [])
        series_names.update(
            [
                s["name"] if "name" in s else f"{i}"
                for i, s in enumerate(series_metadata)
            ]
        )

        if analysis.subject_dispatch.tag is not None:
            nb_tags += 1
        elif analysis.subject_dispatch.topography is not None:
            nb_topographies += 1
        elif analysis.subject_dispatch.surface is not None:
            nb_surfaces += 1
        else:
            nb_others += 1

    series_names = sorted(
        list(series_names)
    )  # index of a name in this list is the "series_name_index"
    visible_series_indices = (
        set()
    )  # elements: series indices, decides whether a series is visible

    #
    # Prepare helpers
    #
    DEFAULT_ALPHA_FOR_TOPOGRAPHIES = 0.3 if has_at_least_one_surface_subject else 1.0

    #
    # Second traversal: Prepare metadata for plotting
    #
    # The plotting is done in Javascript on client side.
    # The metadata is prepared here, the data itself will be retrieved
    # by an AJAX request. The url for this request is also prepared here.
    #
    nb_data_points = 0
    for workflow_idx, analysis in enumerate(analyses_success_list):
        #
        # Define some helper variables
        #
        is_surface_analysis = analysis.subject_dispatch.surface is not None
        is_topography_analysis = analysis.subject_dispatch.topography is not None

        #
        # Change display name depending on whether there is a parent analysis or not
        #
        parent_analysis = None
        if (
            is_topography_analysis
            and analysis.subject_dispatch.topography.surface.num_topographies() > 1
        ):
            for a in analyses_success_list:
                if (
                    a.subject_dispatch.surface is not None
                    and a.subject_dispatch.surface.id
                    == analysis.subject_dispatch.topography.surface.id
                    and a.function.id == analysis.function.id
                ):
                    parent_analysis = a

        subject_display_name = subject_names[workflow_idx]

        #
        # Handle unexpected task states for robustness, shouldn't be needed in general
        #
        if analysis.task_state != analysis.SUCCESS:
            # not ready yet
            continue  # should not happen if only called with successful analyses

        #
        # Find out scale for data
        #
        result_metadata = analysis.result_metadata
        series_metadata = result_metadata.get("series", [])

        messages = []

        if xunit is None:
            analysis_xscale = 1
        else:
            try:
                analysis_xscale = ureg.convert(
                    1, result_metadata.get("xunit", "m"), xunit
                )
            except (UndefinedUnitError, DimensionalityError) as exc:
                err_msg = (
                    f"Cannot convert x units when displaying results for analysis with id {analysis.id}. "
                    f"Cause: {exc}"
                )
                _log.error(err_msg)
                messages.append(dict(alertClass="alert-danger", message=err_msg))
                continue
        if yunit is None:
            analysis_yscale = 1
        else:
            try:
                analysis_yscale = ureg.convert(
                    1, result_metadata.get("yunit", "m"), yunit
                )
            except (UndefinedUnitError, DimensionalityError) as exc:
                err_msg = (
                    f"Cannot convert y units when displaying results for analysis with id {analysis.id}. "
                    f"Cause: {exc}"
                )
                _log.error(err_msg)
                messages.append(dict(alertClass="alert-danger", message=err_msg))
                continue

        for series_idx, s in enumerate(series_metadata):
            series_json_manifest = analysis.folder.find_file(
                f"series-{series_idx}.json"
            )
            series_name = s["name"] if "name" in s else f"{series_idx}"
            series_name_idx = series_names.index(series_name)

            is_visible = s["visible"] if "visible" in s else True
            if is_visible:
                visible_series_indices.add(series_name_idx)
                # as soon as one dataset wants this series to be visible,
                # this series will be visible for all

            #
            # Actually plot the line
            #
            nb_data_points += s["nbDataPoints"] if "nbDataPoints" in s else 0

            # hover_name = "{} for '{}'".format(series_name, topography_name)
            line_width = LINEWIDTH_FOR_SURFACE_AVERAGE if is_surface_analysis else 1
            alpha = DEFAULT_ALPHA_FOR_TOPOGRAPHIES if is_topography_analysis else 1.0

            #
            # Find out whether this dataset for this special series has a parent dataset
            # in the parent_analysis, which means whether the same series is available there
            #
            has_parent = (parent_analysis is not None) and any(
                s["name"] == series_name if "name" in s else f"{i}" == series_name
                for i, s in enumerate(parent_analysis.result_metadata.get("series", []))
            )

            #
            # Context information for this data source, will be interpreted by client JS code
            #
            data_sources_dict += [
                {
                    "sourceName": f"analysis-{analysis.id}",
                    "subjectName": subject_display_name,
                    "subjectNameIndex": workflow_idx,
                    "subjectNameHasParent": parent_analysis is not None,
                    "seriesName": series_name,
                    "seriesNameIndex": series_name_idx,
                    "hasParent": has_parent,  # can be used for the legend
                    "xScaleFactor": analysis_xscale,
                    "yScaleFactor": analysis_yscale,
                    "url": ManifestSerializer(
                        series_json_manifest, context={"request": request}
                    ).data["file"],
                    "width": line_width,
                    "alpha": alpha,
                    "visible": series_name_idx
                    in visible_series_indices,  # independent of subject
                    "isSurfaceAnalysis": is_surface_analysis,
                    "isTopographyAnalysis": is_topography_analysis,
                }
            ]

    plot_configuration["dataSources"] = data_sources_dict
    plot_configuration["categories"] = [
        {
            "title": "Averages / Measurements",
            "key": "subjectName",
        },
        {
            "title": "Data series",
            "key": "seriesName",
        },
    ]
    plot_configuration["showSymbols"] = nb_data_points < MAX_NUM_POINTS_FOR_SYMBOLS

    context["plotConfiguration"] = plot_configuration
    context["messages"] = messages

    return Response(context)


@api_view(["POST"])
def set_name(request, workflow_id: int):
    name = request.data.get("name")
    description = request.data.get("description")
    analysis = get_object_or_404(Analysis, id=workflow_id)
    analysis.set_name(name, description)
    return Response({})


@api_view(["GET"])
def statistics(request):
    stats = {
        "nb_analyses": Analysis.objects.count(),
    }
    if not request.user.is_anonymous:
        stats = {
            **stats,
            "nb_analyses_of_user": Analysis.objects.for_user(request.user).count(),
        }
    return Response(stats)


@api_view(["GET"])
def memory_usage(request):
    m = defaultdict(list)
    for function_id, function_name in AnalysisFunction.objects.values_list(
        "id", "name"
    ):
        max_nb_data_pts = Case(
            When(
                subject_dispatch__surface__isnull=False,
                then=Max(
                    F("subject_dispatch__surface__topography__resolution_x")
                    * Case(
                        When(
                            subject_dispatch__surface__topography__resolution_y__isnull=False,
                            then=F(
                                "subject_dispatch__surface__topography__resolution_y"
                            ),
                        ),
                        default=1,
                    )
                ),
            ),
            default=F("subject_dispatch__topography__resolution_x")
            * Case(
                When(
                    subject_dispatch__topography__resolution_y__isnull=False,
                    then=F("subject_dispatch__topography__resolution_y"),
                ),
                default=1,
            ),
        )
        sum_nb_data_pts = Case(
            When(
                subject_dispatch__surface__isnull=False,
                then=Sum(
                    F("subject_dispatch__surface__topography__resolution_x")
                    * Case(
                        When(
                            subject_dispatch__surface__topography__resolution_y__isnull=False,
                            then=F(
                                "subject_dispatch__surface__topography__resolution_y"
                            ),
                        ),
                        default=1,
                    )
                ),
            ),
            default=F("subject_dispatch__topography__resolution_x")
            * Case(
                When(
                    subject_dispatch__topography__resolution_y__isnull=False,
                    then=F("subject_dispatch__topography__resolution_y"),
                ),
                default=1,
            ),
        )
        for x in (
            Analysis.objects.filter(function_id=function_id)
            .values("task_memory")
            .annotate(
                resolution_x=F("subject_dispatch__topography__resolution_x"),
                resolution_y=F("subject_dispatch__topography__resolution_y"),
                duration=F("end_time") - F("start_time"),
                subject=Case(
                    When(subject_dispatch__tag__isnull=False, then=Value("tag")),
                    When(
                        subject_dispatch__surface__isnull=False, then=Value("surface")
                    ),
                    default=Value("topography"),
                ),
                max_nb_data_pts=max_nb_data_pts,
                sum_nb_data_pts=sum_nb_data_pts,
            )
        ):
            m[function_name] += [x]
    return Response(m, status=200)

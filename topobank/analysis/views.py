import pickle
import json
import os
from typing import Optional, Dict, Any

import numpy as np
import math
import itertools
from collections import OrderedDict, defaultdict

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse, Http404, JsonResponse
from django.views.generic import DetailView, FormView, TemplateView
from django.urls import reverse_lazy
from django.db.models import Q
from django import template
from django.core.files.storage import default_storage
from django.core.cache import cache  # default cache
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, reverse
from django.conf import settings

import bokeh
import bokeh.palettes as palettes
from bokeh.layouts import column, grid, layout
from bokeh.models import ColumnDataSource, CustomJS, TapTool, Circle, HoverTool
from bokeh.models.ranges import DataRange1d
from bokeh.plotting import figure
from bokeh.embed import components, json_item
from bokeh.models.widgets import CheckboxGroup, Tabs, Panel, Toggle, Button
from bokeh.models import LinearColorMapper, ColorBar

import xarray as xr

from pint import UnitRegistry, UndefinedUnitError

from guardian.shortcuts import get_objects_for_user

from trackstats.models import Metric

from ContactMechanics.Tools.ContactAreaAnalysis import patch_areas, assign_patch_numbers

from ..manager.models import Topography, Surface
from ..manager.utils import instances_to_selection, selection_to_subjects_json, subjects_from_json, subjects_to_json
from ..usage_stats.utils import increase_statistics_by_date_and_object
from ..plots import configure_plot
from .models import Analysis, AnalysisFunction, AnalysisCollection, CARD_VIEW_FLAVORS
from .forms import FunctionSelectForm
from .utils import get_latest_analyses, round_to_significant_digits, request_analysis

import logging

_log = logging.getLogger(__name__)

SMALLEST_ABSOLUT_NUMBER_IN_LOGPLOTS = 1e-100
MAX_NUM_POINTS_FOR_SYMBOLS = 50
NUM_SIGNIFICANT_DIGITS_RMS_VALUES = 5
LINEWIDTH_FOR_SURFACE_AVERAGE = 4


def card_view_class(card_view_flavor):
    """Return class for given card view flavor.

    Parameters
    ----------
    card_view_flavor: str
        Defined in model AnalysisFunction.

    Returns
    -------
    class
    """
    if card_view_flavor not in CARD_VIEW_FLAVORS:
        raise ValueError("Unknown card view flavor '{}'. Known values are: {}".format(card_view_flavor,
                                                                                      CARD_VIEW_FLAVORS))

    class_name = card_view_flavor.title().replace(' ', '') + "CardView"
    return globals()[class_name]


def switch_card_view(request):
    """Selects appropriate card view upon request.

    Within the request, there is hint to which function
    the request is related to. Depending on the function,
    another view should be used.

    This view here creates than a new view and let
    it return the response instead.

    The request must have a "function_id" in its
    POST parameters.

    :param request:
    :return: HTTPResponse
    """
    if not request.is_ajax():
        return Http404

    try:
        function_id = int(request.POST.get('function_id'))
    except (KeyError, ValueError, TypeError):
        return HttpResponse("Error in POST arguments")

    function = AnalysisFunction.objects.get(id=function_id)

    view_class = card_view_class(function.card_view_flavor)

    #
    # for statistics, count views per function
    #
    metric = Metric.objects.ANALYSES_RESULTS_VIEW_COUNT
    increase_statistics_by_date_and_object(metric, obj=function)

    return view_class.as_view()(request)


class SimpleCardView(TemplateView):
    """Very basic display of results. Base class for more complex views.

    Must be used in an AJAX call.
    """

    @staticmethod
    def _template_name(class_name, template_flavor):
        template_name_prefix = class_name.replace('View', '').replace('Card', '_card').lower()
        return f"analysis/{template_name_prefix}_{template_flavor}.html"

    def get_template_names(self):
        """Return list of possible templates.

        Uses request parameter 'template_flavor'.
        """
        try:
            template_flavor = self.request.POST.get('template_flavor')
        except (KeyError, ValueError):
            raise ValueError("Cannot read 'template_flavor' from POST arguments.")

        if template_flavor is None:
            raise ValueError("Missing 'template_flavor' in POST arguments.")

        template_name = self._template_name(self.__class__.__name__, template_flavor)

        #
        # If template does not exist, return template from parent class
        #
        # MAYBE later: go down the hierarchy and take first template found
        try:
            template.loader.get_template(template_name)
        except template.TemplateDoesNotExist:
            base_class = self.__class__.__bases__[0]
            template_name = self._template_name(base_class.__name__, template_flavor)

        return [template_name]

    def get_context_data(self, **kwargs):
        """Gets function ids and subject ids from POST parameters.

        :return: dict to be used in analysis card templates' context

        The returned dict has the following keys:

          card_id: A CSS id referencing the card which is to be delivered
          title: card title
          function: AnalysisFunction instance
          unique_kwargs: dict with common kwargs for all analyses, None if not unique
          analyses_available: queryset of all analyses which are relevant for this view
          analyses_success: queryset of successfully finished analyses (result is useable, can be displayed)
          analyses_failure: queryset of analyses finished with failures (result has traceback, can't be displayed)
          analyses_unready: queryset of analyses which are still running
          subjects_missing: list of subjects for which there is no Analysis object yet
          subjects_requested_json: json representation of list with all requested subjects as 2-tuple
                                   (subject_type.id, subject.id)
        """
        context = super().get_context_data(**kwargs)

        request = self.request
        request_method = request.POST
        user = request.user

        try:
            function_id = int(request_method.get('function_id'))
            card_id = request_method.get('card_id')
            subjects_ids_json = request_method.get('subjects_ids_json')
        except Exception as exc:
            _log.error("Cannot decode POST arguments from analysis card request. Details: %s", exc)
            raise

        function = AnalysisFunction.objects.get(id=function_id)

        # Calculate subjects for the analyses, filtered for those which have an implementation
        subjects_requested = subjects_from_json(subjects_ids_json, function=function)

        # The following is needed for re-triggering analyses, now filtered
        # in order to trigger only for subjects which have an implementation
        subjects_ids_json = subjects_to_json(subjects_requested)

        #
        # Get all relevant analysis objects for this function and these subjects
        #

        analyses_avail = get_latest_analyses(user, function, subjects_requested)

        #
        # Filter for analyses where the user has read permission for the related surface
        #
        readable_surfaces = get_objects_for_user(user, ['view_surface'], klass=Surface)
        analyses_avail = analyses_avail.filter(Q(topography__surface__in=readable_surfaces)) | \
                         analyses_avail.filter(Q(surface__in=readable_surfaces))

        #
        # collect list of subjects for which an analysis instance is missing
        #
        subjects_available = [a.subject for a in analyses_avail]
        subjects_missing = [s for s in subjects_requested if s not in subjects_available]

        #
        # collect all keyword arguments and check whether they are equal
        #
        unique_kwargs: Dict[ContentType, Optional[Any]] = {}  # key: ContentType, value: dict or None
        # - if a contenttype is missing as key, this means:
        #   There are no analyses available for this contenttype
        # - if a contenttype exists, but value is None, this means:
        #   There arguments of the analyses for this contenttype are not unique

        for av in analyses_avail:
            kwargs = pickle.loads(av.kwargs)

            if av.subject_type not in unique_kwargs:
                unique_kwargs[av.subject_type] = kwargs
            elif unique_kwargs[av.subject_type] is not None:  # was unique so far
                if kwargs != unique_kwargs[av.subject_type]:
                    unique_kwargs[av.subject_type] = None
                    # Found differing arguments for this subject_type
                    # We need to continue in the loop, because of the other subject types

        function = AnalysisFunction.objects.get(id=function_id)

        #
        # automatically trigger analyses for missing subjects (topographies or surfaces)
        #
        # Save keyword arguments which should be used for missing analyses,
        # sorted by subject type
        kwargs_for_missing = {}
        for st in function.get_implementation_types():
            try:
                kw = unique_kwargs[st]
                if kw is None:
                    kw = {}
            except KeyError:
                kw = function.get_default_kwargs(st)
            kwargs_for_missing[st] = kw

        # For every possible implemented subject type the following is done:
        # We use the common unique keyword arguments if there are any; if not
        # the default arguments for the implementation is used

        subjects_triggered = []
        for subject in subjects_missing:
            if subject.is_shared(user):
                ct = ContentType.objects.get_for_model(subject)
                analysis_kwargs = kwargs_for_missing[ct]
                triggered_analysis = request_analysis(user, function, subject, **analysis_kwargs)
                subjects_triggered.append(subject)
                # topographies_available_ids.append(topo.id)
                _log.info(f"Triggered analysis {triggered_analysis.id} for function '{function.name}' "
                          f"and subject '{subject}'.")
        subjects_missing = [s for s in subjects_missing if s not in subjects_triggered]

        # now all subjects which needed to be triggered, should have been triggered
        # with common arguments if possible
        # collect information about available analyses again
        if len(subjects_triggered) > 0:

            # if no analyses where available before, unique_kwargs is None
            # which is interpreted as "differing arguments". This is wrong
            # in that case
            if len(analyses_avail) == 0:
                unique_kwargs = kwargs_for_missing

            analyses_avail = get_latest_analyses(user, function_id, subjects_requested) \
                .filter(Q(topography__surface__in=readable_surfaces) |
                        Q(surface__in=readable_surfaces))

        #
        # Determine status code of request - do we need to trigger request again?
        #
        analyses_ready = analyses_avail.filter(task_state__in=['su', 'fa'])
        analyses_unready = analyses_avail.filter(~Q(id__in=analyses_ready))

        #
        # collect lists of successful analyses and analyses with failures
        #
        # Only the successful ones should show up in the plot
        # the ones with failure should be shown elsewhere
        analyses_success = analyses_ready.filter(task_state='su')
        analyses_failure = analyses_ready.filter(task_state='fa')

        #
        # comprise context for analysis result card
        #
        context.update(dict(
            bokeh_version=bokeh.__version__,  # is there a way to inject this globally?
            card_id=card_id,
            title=function.name,
            function=function,
            unique_kwargs=unique_kwargs,
            analyses_available=analyses_avail,  # all Analysis objects related to this card
            analyses_success=analyses_success,  # ..the ones which were successful and can be displayed
            analyses_failure=analyses_failure,  # ..the ones which have failures and can't be displayed
            analyses_unready=analyses_unready,  # ..the ones which are still running
            subjects_missing=subjects_missing,  # subjects for which there is no Analysis object yet
            subjects_ids_json=subjects_ids_json,  # can be used to re-trigger analyses
            extra_warnings=[],  # use list of dicts of form {'alert_class': 'alert-info', 'message': 'your message'}
        ))

        return context

    def post(self, request, *args, **kwargs):
        """
        Returns status code

        - 200 if all analysis are finished (success or failure).
        - 202 if there are still analyses which not have been finished,
          this can be used to request the card again later

        :param request:
        :param args:
        :param kwargs:
        :return:
        """
        response = super().get(request, *args, **kwargs)

        #
        # Set status code depending on whether all analyses are finished
        #
        context = response.context_data
        num_analyses_avail = context['analyses_available'].count()
        num_analyses_ready = context['analyses_success'].count() + context['analyses_failure'].count()

        if (num_analyses_avail > 0) and (num_analyses_ready < num_analyses_avail):
            response.status_code = 202  # signal to caller: please request again
        else:
            response.status_code = 200  # request is as complete as possible

        return response


class PlotCardView(SimpleCardView):

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        analyses_success = context['analyses_success']

        #
        # order analyses such that surface analyses are coming last (plotted on top)
        #
        surface_ct = ContentType.objects.get_for_model(Surface)
        analyses_success_list = []
        for surface_analysis in analyses_success.filter(subject_type=surface_ct):
            if surface_analysis.subject.num_topographies() > 1:
                # only show average for surface if more than one topography
                analyses_success_list.append(surface_analysis)
        for topography_analysis in analyses_success.filter(~Q(subject_type=surface_ct)):
            try:
                surface_analysis = analyses_success.get(subject_id=topography_analysis.subject.surface.id,
                                                        subject_type=surface_ct)
                i = [s.subject.id if s.subject_type == surface_ct else None for s in analyses_success_list] \
                    .index(surface_analysis.subject.id)
            except Analysis.DoesNotExist:
                analyses_success_list.append(topography_analysis)
            else:
                analyses_success_list.insert(i + 1, topography_analysis)

        data_sources_dict = []

        # Special case: It can happen that there is one surface with a successful analysis
        # but the only measurement's analysis has no success. In this case there is also
        # no successful analysis to display because the surface has only one measurement.

        nb_analyses = len(analyses_success_list)
        if nb_analyses == 0:
            #
            # Prepare plot, controls, and table with special values..
            #
            context.update(
                dict(plot_script="",
                     plot_div="No successfully finished analyses available",
                     special_values=[],
                     topography_colors=json.dumps(list()),
                     series_dashes=json.dumps(list())))
            return context

        #
        # Build order of subjects such that surfaces are first (used for checkbox on subjects)
        #
        subjects = set(a.subject for a in analyses_success_list)
        subjects = sorted(subjects, key=lambda s: s.get_content_type() == surface_ct, reverse=True)  # surfaces first
        subject_names_for_plot = []

        # Build subject groups by content type, so each content type gets its
        # one checkbox group

        subject_checkbox_groups = {}  # key: ContentType, value: list of subject names to display

        for s in subjects:
            subject_ct = s.get_content_type()
            subject_name = s.label
            if subject_ct == surface_ct:
                subject_name = f"Average of »{subject_name}«"
            subject_names_for_plot.append(subject_name)

            if subject_ct not in subject_checkbox_groups.keys():
                subject_checkbox_groups[subject_ct] = []

            subject_checkbox_groups[subject_ct].append(subject_name)

        has_at_least_one_surface_subject = surface_ct in subject_checkbox_groups.keys()

        #
        # Use first analysis to determine some properties for the whole plot
        #

        first_analysis_result = analyses_success_list[0].result
        xunit = first_analysis_result['xunit'] if 'xunit' in first_analysis_result else None
        yunit = first_analysis_result['yunit'] if 'yunit' in first_analysis_result else None

        ureg = UnitRegistry()  # for unit conversion for each analysis individually, see below

        def get_axis_type(key):
            return first_analysis_result.get(key) or "linear"

        x_axis_label = first_analysis_result['xlabel']
        if xunit is not None:
            x_axis_label += f' ({xunit})'
        y_axis_label = first_analysis_result['ylabel']
        if yunit is not None:
            y_axis_label += f' ({yunit})'

        #
        # Context information for the figure
        #
        context.update(dict(
            x_axis_label=x_axis_label,
            y_axis_label=y_axis_label,
            x_axis_type=get_axis_type('xscale'),
            y_axis_type=get_axis_type('yscale'),
            output_backend=settings.BOKEH_OUTPUT_BACKEND))


        #
        # First traversal: find all available series names and sort them
        # We need fixed series indices, because this is used on Javascript level to connect
        # checkboxes to glyphs.
        #
        series_names = set()
        nb_surfaces = 0  # Total number of averages/surfaces shown
        nb_topographies = 0  # Total number of topography results shown
        for analysis in analyses_success_list:
            #
            # handle task state
            #
            if analysis.task_state != analysis.SUCCESS:
                continue  # should not happen if only called with successful analyses

            series_names.update([s['name'] for s in analysis.result['series']])

            if isinstance(analysis.subject, Surface):
                nb_surfaces += 1
            else:
                nb_topographies += 1

        series_names = sorted(list(series_names))  # index of a name in this list is the "series_idx"
        series_visible = set()  # elements: series indices, decides whether a series is visible

        #
        # Prepare helpers for dashes and colors
        #
        surface_color_palette = palettes.Greys256  # surfaces are shown in black/grey
        if nb_topographies <= 10:
            topography_colors = palettes.Category10_10
        else:
            topography_colors = [palettes.Plasma256[k*256//nb_topographies] for k in range(nb_topographies)]
            # we don't want to have yellow as first color
            topography_colors = topography_colors[nb_topographies//2:] + topography_colors[:nb_topographies//2]
        dash_cycle = itertools.cycle(['solid', 'dashed', 'dotted', 'dotdash', 'dashdot'])

        subject_colors = OrderedDict()  # key: subject instance, value: color

        series_dashes = OrderedDict()  # key: series name

        DEFAULT_ALPHA_FOR_TOPOGRAPHIES = 0.3 if has_at_least_one_surface_subject else 1.0

        #
        # Second traversal: do the plotting
        #
        surface_index = -1
        topography_index = -1
        for a_index, analysis in enumerate(analyses_success_list):
            #
            # Define some helper variables
            #
            subject = analysis.subject
            subject_idx = subjects.index(subject)  # unique identifier within the plot

            is_surface_analysis = isinstance(subject, Surface)
            is_topography_analysis = isinstance(subject, Topography)

            if is_topography_analysis:
                try:
                    analyses_success.get(subject_id=analysis.subject.surface.id, subject_type=surface_ct)
                except Analysis.DoesNotExist:
                    has_parent = False
                else:
                    has_parent = True

            if is_surface_analysis:
                # Surface results are plotted in black/grey
                surface_index += 1
                subject_colors[subject] = \
                    surface_color_palette[surface_index * len(surface_color_palette) // nb_surfaces]
            else:
                topography_index += 1
                subject_colors[subject] = topography_colors[topography_index]

            subject_display_name = subject_names_for_plot[subject_idx]
            if is_topography_analysis and has_parent:
                subject_display_name = f"└─ {subject_display_name}"

            #
            # handle task state
            #
            if analysis.task_state == analysis.FAILURE:
                continue  # should not happen if only called with successful analyses
            elif analysis.task_state == analysis.SUCCESS:
                series = analysis.result['series']
            else:
                # not ready yet
                continue  # should not happen if only called with successful analyses

            #
            # find out scale for data
            #
            analysis_result = analysis.result

            if xunit is None:
                analysis_xscale = 1
            else:
                try:
                    analysis_xscale = ureg.convert(1, analysis_result['xunit'], xunit)
                except UndefinedUnitError as exc:
                    _log.error("Cannot convert units when displaying results for analysis with id %s. Cause: %s",
                               analysis.id, str(exc))
                    continue
                    # TODO How to handle such an error here? Notification? Message in analysis box?
            if yunit is None:
                analysis_yscale = 1
            else:
                try:
                    analysis_yscale = ureg.convert(1, analysis_result['yunit'], yunit)
                except UndefinedUnitError as exc:
                    _log.error("Cannot convert units when displaying results for analysis with id %s. Cause: %s",
                               analysis.id, str(exc))
                    continue
                    # TODO How to handle such an error here? Notification? Message in analysis box?

            for s_index, s in enumerate(series):
                #
                # Collect data for visibility of the corresponding series
                #
                series_name = s['name']
                is_visible = s['visible'] if 'visible' in s else True
                series_idx = series_names.index(series_name)
                if is_visible:
                    series_visible.add(series_idx)
                    # as soon as one dataset wants this series to be visible,
                    # this series will be visible for all

                #
                # find out dashes for data series
                #
                if series_name not in series_dashes:
                    series_dashes[series_name] = next(dash_cycle)
                    # series_symbols[series_name] = next(symbol_cycle)

                #
                # Actually plot the line
                #
                try:
                    len_x = len(s['x'])
                except TypeError:  # sometimes s['x'] is only one int
                    len_x = 1
                show_symbols = len_x <= MAX_NUM_POINTS_FOR_SYMBOLS

                legend_entry = subject_display_name + ": " + series_name

                curr_color = subject_colors[subject]
                curr_dash = series_dashes[series_name]
                # curr_symbol = series_symbols[series_name]

                # hover_name = "{} for '{}'".format(series_name, topography_name)
                line_width = LINEWIDTH_FOR_SURFACE_AVERAGE if is_surface_analysis else 1
                topo_alpha = DEFAULT_ALPHA_FOR_TOPOGRAPHIES if is_topography_analysis else 1.

                #
                # Context information for this data source
                #
                data_sources_dict += [dict(
                    source_name=f'analysis-{analysis.id}',
                    name=subject_display_name,
                    name_index=a_index,
                    series=series_name,
                    series_index=series_idx,
                    xScaleFactor=analysis_xscale,
                    yScaleFactor=analysis_yscale,
                    url=default_storage.url(f'{analysis.storage_prefix}/{s_index}.json'),
                    color=curr_color,
                    dash=curr_dash,
                    width=line_width,
                    alpha=topo_alpha,
                    showSymbols=show_symbols,
                    visible=series_idx in series_visible,
                    is_surface_analysis=is_surface_analysis,
                    is_topography_analysis=is_topography_analysis
                )]

        context['data_sources'] = json.dumps(data_sources_dict)

        return context


class ContactMechanicsCardView(SimpleCardView):

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        alerts = []  # list of collected alerts
        analyses_success = context['analyses_success']

        if len(analyses_success) > 0:
            data_sources_dict = []
            color_cycle = itertools.cycle(palettes.Category10_10)

            #
            # Context information for the figure
            #
            context.update(dict(
                output_backend=settings.BOKEH_OUTPUT_BACKEND))

            #
            # Generate two plots in two tabs based on same data sources
            #
            for a_index, analysis in enumerate(analyses_success):
                curr_color = next(color_cycle)

                #
                # Context information for this data source
                #
                data_sources_dict += [dict(
                    source_name=f'analysis-{analysis.id}',
                    name=analysis.subject.name,
                    name_index=a_index,
                    url=default_storage.url(f'{analysis.storage_prefix}/result.json'),
                    color=curr_color,
                )]

            context['data_sources'] = json.dumps(data_sources_dict)

        #
        # Calculate initial values for the parameter form on the page
        # We only handle topographies here so far, so we only take into account
        # parameters for topography analyses
        #
        topography_ct = ContentType.objects.get_for_model(Topography)
        try:
            unique_kwargs = context['unique_kwargs'][topography_ct]
        except KeyError:
            unique_kwargs = None
        if unique_kwargs:
            initial_calc_kwargs = unique_kwargs
        else:
            # default initial arguments for form if we don't have unique common arguments
            contact_mechanics_func = AnalysisFunction.objects.get(name="Contact mechanics")
            initial_calc_kwargs = contact_mechanics_func.get_default_kwargs(topography_ct)
            initial_calc_kwargs['substrate_str'] = 'nonperiodic'  # because most topographies are non-periodic

        context['initial_calc_kwargs'] = initial_calc_kwargs

        context['extra_warnings'] = alerts
        context['extra_warnings'].append(
            dict(alert_class='alert-warning',
                 message="""
                 Translucent data points did not converge within iteration limit and may carry large errors.
                 <i>A</i> is the true contact area and <i>A0</i> the apparent contact area,
                 i.e. the size of the provided measurement.""")
        )

        context['limits_calc_kwargs'] = settings.CONTACT_MECHANICS_KWARGS_LIMITS

        return context


class RoughnessParametersCardView(SimpleCardView):

    @staticmethod
    def _convert_value(v):
        if v is not None:
            if math.isnan(v):
                v = None  # will be interpreted as null in JS, replace there with NaN!
                # It's not easy to pass NaN as JSON:
                # https://stackoverflow.com/questions/15228651/how-to-parse-json-string-containing-nan-in-node-js
            elif math.isinf(v):
                return 'infinity'
            else:
                # convert float32 to float, round to fixed number of significant digits
                v = round_to_significant_digits(float(v),
                                                NUM_SIGNIFICANT_DIGITS_RMS_VALUES)
        return v

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        analyses_success = context['analyses_success']

        data = []
        for analysis in analyses_success:
            analysis_result = analysis.result

            for d in analysis_result:
                d['value'] = self._convert_value(d['value'])

                if not d['direction']:
                    d['direction'] = ''
                if not d['from']:
                    d['from'] = ''
                if not d['symbol']:
                    d['symbol'] = ''

                # put topography in every line
                topo = analysis.subject
                d.update(dict(topography_name=topo.name,
                              topography_url=topo.get_absolute_url()))

            data.extend(analysis_result)

        #
        # find out all existing keys keeping order
        #
        all_keys = []
        for d in data:
            for k in d.keys():
                if k not in all_keys:
                    all_keys.append(k)

        #
        # make sure every dict has all keys
        #
        for k in all_keys:
            for d in data:
                d.setdefault(k)

        #
        # create table
        #
        context.update(dict(
            table_data=data
        ))

        return context


def submit_analyses_view(request):
    """Requests analyses.
    :param request:
    :return: HTTPResponse
    """
    if not request.is_ajax():
        raise Http404

    request_method = request.POST
    user = request.user

    if user.is_anonymous:
        raise PermissionDenied()

    # args_dict = request_method
    try:
        function_id = int(request_method.get('function_id'))
        subjects_ids_json = request_method.get('subjects_ids_json')
        function_kwargs_json = request_method.get('function_kwargs_json')
        function_kwargs = json.loads(function_kwargs_json)
        subjects = subjects_from_json(subjects_ids_json)
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({'error': 'error in request data'}, status=400)

    #
    # Interpret given arguments
    #
    function = AnalysisFunction.objects.get(id=function_id)

    allowed = True
    for subject in subjects:
        allowed &= subject.is_shared(user)
        if not allowed:
            break

    if allowed:
        analyses = [request_analysis(user, function, subject, **function_kwargs) for subject in subjects]

        status = 200

        #
        # create a collection of analyses such that points to all analyses
        #
        collection = AnalysisCollection.objects.create(name=f"{function.name} for {len(subjects)} subjects.",
                                                       combined_task_state=Analysis.PENDING,
                                                       owner=user)
        collection.analyses.set(analyses)
        #
        # Each finished analysis checks whether related collections are finished, see "topobank.taskapp.tasks"
        #
    else:
        status = 403

    return JsonResponse({}, status=status)


def _contact_mechanics_geometry_figure(values, frame_width, frame_height, topo_unit, topo_size, colorbar_title=None,
                                       value_unit=None):
    """

    :param values: 2D numpy array
    :param frame_width:
    :param frame_height:
    :param topo_unit:
    :param topo_size:
    :param colorbar_title:
    :param value_unit:
    :return:
    """

    x_range = DataRange1d(start=0, end=topo_size[0], bounds='auto', range_padding=5)
    y_range = DataRange1d(start=topo_size[1], end=0, flipped=True, range_padding=5)

    boolean_values = values.dtype == np.bool

    COLORBAR_WIDTH = 50
    COLORBAR_LABEL_STANDOFF = 12

    plot_width = frame_width
    if not boolean_values:
        plot_width += COLORBAR_WIDTH + COLORBAR_LABEL_STANDOFF + 5

    p = figure(x_range=x_range,
               y_range=y_range,
               frame_width=frame_width,
               frame_height=frame_height,
               plot_width=plot_width,
               x_axis_label="Position x ({})".format(topo_unit),
               y_axis_label="Position y ({})".format(topo_unit),
               match_aspect=True,
               toolbar_location="above",
               output_backend=settings.BOKEH_OUTPUT_BACKEND)

    if boolean_values:
        color_mapper = LinearColorMapper(palette=["black", "white"], low=0, high=1)
    else:
        min_val = values.min()
        max_val = values.max()

        color_mapper = LinearColorMapper(palette='Viridis256', low=min_val, high=max_val)

    p.image([np.rot90(values)], x=0, y=topo_size[1], dw=topo_size[0], dh=topo_size[1], color_mapper=color_mapper)

    if not boolean_values:
        colorbar = ColorBar(color_mapper=color_mapper,
                            label_standoff=COLORBAR_LABEL_STANDOFF,
                            width=COLORBAR_WIDTH,
                            location=(0, 0),
                            title=f"{colorbar_title} ({value_unit})")
        p.add_layout(colorbar, "right")

    configure_plot(p)

    return p


def _contact_mechanics_distribution_figure(values, x_axis_label, y_axis_label,
                                           frame_width, frame_height,
                                           x_axis_type='auto',
                                           y_axis_type='auto',
                                           title=None):
    hist, edges = np.histogram(values, density=True, bins=50)

    p = figure(title=title,
               frame_width=frame_width,
               frame_height=frame_height,
               sizing_mode='scale_width',
               x_axis_label=x_axis_label,
               y_axis_label=y_axis_label,
               x_axis_type=x_axis_type,
               y_axis_type=y_axis_type,
               toolbar_location="above",
               output_backend=settings.BOKEH_OUTPUT_BACKEND)

    p.step(edges[:-1], hist, mode="before", line_width=2)

    configure_plot(p)

    return p


def data(request, pk, location):
    try:
        pk = int(pk)
    except ValueError:
        raise Http404()

    analysis = Analysis.objects.get(id=pk)

    if not request.user.has_perm('view_surface', analysis.related_surface):
        raise PermissionDenied()

    # okay, we have a valid analysis and the user is allowed to see it

    name = f'{analysis.storage_prefix}/{location}'
    url = default_storage.url(name)
    return redirect(url)


def extra_tabs_if_single_item_selected(topographies, surfaces):
    """Return contribution to context for opening extra tabs if a single topography/surface is selected.

    Parameters
    ----------
    topographies: list of topographies
        Use here the result of function `utils.selected_instances`.

    surfaces: list of surfaces
        Use here the result of function `utils.selected_instances`.

    Returns
    -------
    Sequence of dicts, each dict corresponds to an extra tab.

    """
    tabs = []

    if len(topographies) == 1 and len(surfaces) == 0:
        # exactly one topography was selected -> show also tabs of topography
        topo = topographies[0]
        tabs.extend([
            {
                'title': f"{topo.surface.label}",
                'icon': "gem",
                'icon_style_prefix': 'far',
                'href': reverse('manager:surface-detail', kwargs=dict(pk=topo.surface.pk)),
                'active': False,
                'login_required': False,
                'tooltip': f"Properties of surface '{topo.surface.label}'",
            },
            {
                'title': f"{topo.name}",
                'icon': "file",
                'icon_style_prefix': 'far',
                'href': reverse('manager:topography-detail', kwargs=dict(pk=topo.pk)),
                'active': False,
                'login_required': False,
                'tooltip': f"Properties of measurement '{topo.name}'",
            }
        ])
    elif len(surfaces) == 1 and all(t.surface == surfaces[0] for t in topographies):
        # exactly one surface was selected -> show also tab of surface
        surface = surfaces[0]
        tabs.append(
            {
                'title': f"{surface.label}",
                'icon': 'gem',
                'icon_style_prefix': 'far',
                'href': reverse('manager:surface-detail', kwargs=dict(pk=surface.pk)),
                'active': False,
                'login_required': False,
                'tooltip': f"Properties of surface '{surface.label}'",
            }
        )
    return tabs


class AnalysisFunctionDetailView(DetailView):
    """Show analyses for a given analysis function.
    """
    model = AnalysisFunction
    template_name = "analysis/analyses_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        function = self.object

        effective_topographies, effective_surfaces, subjects_ids_json = selection_to_subjects_json(self.request)

        card = dict(function=function,
                    subjects_ids_json=subjects_ids_json)

        context['card'] = card

        # Decide whether to open extra tabs for surface/topography details
        tabs = extra_tabs_if_single_item_selected(effective_topographies, effective_surfaces)
        tabs.extend([
            {
                'title': f"Analyze",
                'icon': "chart-area",
                'href': reverse('analysis:list'),
                'active': False,
                'login_required': False,
                'tooltip': "Results for selected analysis functions",
            },
            {
                'title': f"{function.name}",
                'icon': "chart-area",
                'href': self.request.path,
                'active': True,
                'login_required': False,
                'tooltip': f"Results for analysis '{function.name}'",
                'show_basket': True,
            }
        ])
        context['extra_tabs'] = tabs

        return context


class AnalysesListView(FormView):
    """View showing analyses from multiple functions.
    """
    form_class = FunctionSelectForm
    success_url = reverse_lazy('analysis:list')
    template_name = "analysis/analyses_list.html"

    def get_initial(self):

        user = self.request.user

        if 'collection_id' in self.kwargs:
            collection_id = self.kwargs['collection_id']
            try:
                collection = AnalysisCollection.objects.get(id=collection_id)
            except AnalysisCollection.DoesNotExist:
                raise Http404("Collection does not exist")

            if collection.owner != user:
                raise PermissionDenied()

            functions = set(a.function for a in collection.analyses.all())
            topographies = set(a.subject for a in collection.analyses.all())

            # as long as we have the current UI (before implementing GH #304)
            # we also set the collection's function and topographies as selection
            # TODO is this still needed?
            topography_selection = instances_to_selection(topographies=topographies)
            self.request.session['selection'] = tuple(topography_selection)
            self.request.session['selected_functions'] = tuple(f.id for f in functions)

        elif 'surface_id' in self.kwargs:
            surface_id = self.kwargs['surface_id']
            try:
                surface = Surface.objects.get(id=surface_id)
            except Surface.DoesNotExist:
                raise PermissionDenied()

            if not user.has_perm('view_surface', surface):
                raise PermissionDenied()

            #
            # So we have an existing surface and are allowed to view it, so we select it
            #
            self.request.session['selection'] = ['surface-{}'.format(surface_id)]

        elif 'topography_id' in self.kwargs:
            topo_id = self.kwargs['topography_id']
            try:
                topo = Topography.objects.get(id=topo_id)
            except Topography.DoesNotExist:
                raise PermissionDenied()

            if not user.has_perm('view_surface', topo.surface):
                raise PermissionDenied()

            #
            # So we have an existing topography and are allowed to view it, so we select it
            #
            self.request.session['selection'] = ['topography-{}'.format(topo_id)]

        return dict(
            functions=AnalysesListView._selected_functions(self.request),
        )

    def post(self, request, *args, **kwargs):  # TODO is this really needed?
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def form_valid(self, form):
        functions = form.cleaned_data.get('functions', [])
        self.request.session['selected_functions'] = list(t.id for t in functions)
        return super().form_valid(form)

    @staticmethod
    def _selected_functions(request):
        """Returns selected functions as saved in session or, if given, in POST parameters.
        """
        function_ids = request.session.get('selected_functions', [])
        functions = AnalysisFunction.objects.filter(id__in=function_ids)
        return functions

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        selected_functions = self._selected_functions(self.request)

        effective_topographies, effective_surfaces, subjects_ids_json = selection_to_subjects_json(self.request)

        # for displaying result card, we need a dict for each card,
        # which then can be used to load the result data in the background
        cards = []
        for function in selected_functions:
            cards.append(dict(function=function,
                              subjects_ids_json=subjects_ids_json))

        context['cards'] = cards

        # Decide whether to open extra tabs for surface/topography details
        tabs = extra_tabs_if_single_item_selected(effective_topographies, effective_surfaces)
        tabs.append(
            {
                'title': f"Analyze",
                'icon': "chart-area",
                'icon-style-prefix': 'fas',
                'href': self.request.path,
                'active': True,
                'login_required': False,
                'tooltip': "Results for selected analysis functions",
                'show_basket': True,
            }
        )
        context['extra_tabs'] = tabs

        return context

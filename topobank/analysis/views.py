import pickle
import json
import os
from typing import Optional, Dict, Any

import numpy as np
import math
import itertools
from collections import OrderedDict, defaultdict

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

import django_tables2 as tables

from bokeh.layouts import row, column, grid, layout
from bokeh.models import ColumnDataSource, CustomJS, TapTool, Circle, HoverTool
from bokeh.palettes import Category10
from bokeh.models.ranges import DataRange1d
from bokeh.plotting import figure
from bokeh.embed import components, json_item
from bokeh.models.widgets import CheckboxGroup, Tabs, Panel, Toggle, Div, Slider, Button
from bokeh.models import LinearColorMapper, ColorBar
from bokeh.models.formatters import FuncTickFormatter

import xarray as xr

from pint import UnitRegistry, UndefinedUnitError

from guardian.shortcuts import get_objects_for_user, get_anonymous_user

from trackstats.models import Metric

from ContactMechanics.Tools.ContactAreaAnalysis import patch_areas, assign_patch_numbers

from ..manager.models import Topography, Surface
from ..manager.utils import selected_instances, instances_to_selection, instances_to_topographies, \
    selection_to_subjects_json, subjects_from_json, subjects_to_json
from ..usage_stats.utils import increase_statistics_by_date_and_object
from ..plots import configure_plot
from .models import Analysis, AnalysisFunction, AnalysisCollection, CARD_VIEW_FLAVORS, ImplementationMissingException
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
                _log.info(f"Triggered analysis {triggered_analysis.id} for function {function.name} " + \
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
        topography_ct = ContentType.objects.get_for_model(Topography)
        surface_ct = ContentType.objects.get_for_model(Surface)
        analyses_success_list = list(analyses_success.filter(~Q(subject_type=surface_ct)))

        for surface_analysis in analyses_success.filter(subject_type=surface_ct):
            if surface_analysis.subject.num_topographies() > 1:
                # only show average for surface if more than one topography
                analyses_success_list.append(surface_analysis)

        # Special case: It can happen that there is one surface with a successful analysis
        # but the only measurement's analysis has no success. In this case there is also
        # no successful analysis to display because the surface has only one measurement.

        if len(analyses_success_list) == 0:
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

        subject_checkbox_groups = {}   # key: ContentType, value: list of subject names to display

        for s in subjects:
            subject_ct = s.get_content_type()
            subject_name = s.label
            if subject_ct == surface_ct:
                subject_name = f"Average of {subject_name}"
            subject_names_for_plot.append(subject_name)

            if subject_ct not in subject_checkbox_groups.keys():
                subject_checkbox_groups[subject_ct] = []

            subject_checkbox_groups[subject_ct].append(subject_name)

        has_at_least_one_surface_subject = surface_ct in subject_checkbox_groups.keys()
        if has_at_least_one_surface_subject:
            num_surface_subjects = len(subject_checkbox_groups[surface_ct])
        else:
            num_surface_subjects = 0
        has_at_least_one_topography_subject = topography_ct in subject_checkbox_groups.keys()

        #
        # Use first analysis to determine some properties for the whole plot
        #

        first_analysis_result = analyses_success_list[0].result_obj
        xunit = first_analysis_result['xunit'] if 'xunit' in first_analysis_result else None
        yunit = first_analysis_result['yunit'] if 'yunit' in first_analysis_result else None

        ureg = UnitRegistry()  # for unit conversion for each analysis individually, see below

        #
        # set xrange, yrange -> automatic bounds for zooming
        #
        x_range = DataRange1d(bounds='auto')  # if min+max not given, calculate from data of render
        y_range = DataRange1d(bounds='auto')

        def get_axis_type(key):
            return first_analysis_result.get(key) or "linear"

        x_axis_label = first_analysis_result['xlabel']
        if xunit is not None:
            x_axis_label += f' ({xunit})'
        y_axis_label = first_analysis_result['ylabel']
        if yunit is not None:
            y_axis_label += f' ({yunit})'

        #
        # Create the plot figure
        #
        plot = figure(plot_height=300,
                      sizing_mode='scale_width',
                      x_range=x_range,
                      y_range=y_range,
                      x_axis_label=x_axis_label,
                      y_axis_label=y_axis_label,
                      x_axis_type=get_axis_type('xscale'),
                      y_axis_type=get_axis_type('yscale'),
                      tools="pan,reset,save,wheel_zoom,box_zoom,hover")

        #
        # Configure hover tool
        #
        plot.hover.tooltips = [
            ("subject name", "$name"),
            ("series", "@series"),
            (x_axis_label, "@x"),
            (y_axis_label, "@y"),
        ]

        #
        # Prepare helpers for dashes and colors
        #
        color_cycle = itertools.cycle(Category10[10])
        dash_cycle = itertools.cycle(['solid', 'dashed', 'dotted', 'dotdash', 'dashdot'])
        # symbol_cycle = itertools.cycle(['circle', 'triangle', 'diamond', 'square', 'asterisk'])
        # TODO remove code for toggling symbols if not needed

        subject_colors = OrderedDict()  # key: subject instance, value: color

        series_dashes = OrderedDict()  # key: series name
        series_names = []
        series_visible = set()  # names of visible series on initial load, needed for checkboxes

        DEFAULT_ALPHA_FOR_TOPOGRAPHIES = 0.3 if has_at_least_one_surface_subject else 1.0

        # Also give each series a symbol (only used for small number of points)
        # series_symbols = OrderedDict()  # key: series name

        #
        # Traverse analyses and plot lines
        #
        js_code_toggle_callback = ""  # callback code if user clicks on checkbox to toggle lines
        js_code_alpha_callback = ""  # callback code if user changes alpha value by slider
        js_args = {}

        special_values = []  # elements: tuple(subject, quantity name, value, unit string)
        alerts = []  # elements: dict with keys 'alert_class' and 'message'

        #
        # First traversal: find all available series names and sort them
        # We need fixed series indices, because this is used on Javascript level to connect
        # checkboxes to glyphs.
        #
        series_names = set()
        for analysis in analyses_success_list:
            analysis_result = analysis.result_obj
            #
            # handle task state
            #
            if analysis.task_state == analysis.FAILURE:
                continue  # should not happen if only called with successful analyses
            elif analysis.task_state == analysis.SUCCESS:
                series = analysis.result_obj['series']
            else:
                # not ready yet
                continue  # should not happen if only called with successful analyses
            for s in series:
                series_names.add(s['name'])

        series_names = sorted(list(series_names))  # index of a name in this list is the "series_idx"
        series_visible = set()  # elements: series indices, decides whether a series is visible
        series_glyphs = defaultdict(list)  # key: series_idx, value: list of glyphs for that series

        #
        # Second traversal: do the plotting
        #
        for analysis in analyses_success_list:

            #
            # Define some helper variables
            #
            subject = analysis.subject
            subject_idx = subjects.index(subject)  # unique identifier within the plot
            subject_colors[subject] = next(color_cycle)

            is_surface_analysis = isinstance(subject, Surface)
            is_topography_analysis = isinstance(subject, Topography)

            subject_display_name = subject_names_for_plot[subject_idx]
            if is_topography_analysis:
                subject_display_name += f", surface: {subject.surface.name}"

            #
            # handle task state
            #
            if analysis.task_state == analysis.FAILURE:
                continue  # should not happen if only called with successful analyses
            elif analysis.task_state == analysis.SUCCESS:
                series = analysis.result_obj['series']
            else:
                # not ready yet
                continue  # should not happen if only called with successful analyses

            #
            # find out scale for data
            #
            analysis_result = analysis.result_obj

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

            for s in series:
                # One could use AjaxDataSource for retrieving the results, but useful if we are already in AJAX call?
                xarr = np.array(s['x'])
                yarr = np.array(s['y'])

                # if logplot, filter all zero values
                mask = np.zeros(xarr.shape, dtype=bool)
                if get_axis_type('xscale') == 'log':
                    mask |= np.isclose(xarr, 0, atol=SMALLEST_ABSOLUT_NUMBER_IN_LOGPLOTS)
                    mask |= np.isnan(xarr)  # sometimes nan is a problem here
                if get_axis_type('yscale') == 'log':
                    mask |= np.isclose(yarr, 0, atol=SMALLEST_ABSOLUT_NUMBER_IN_LOGPLOTS)
                    mask |= np.isnan(yarr)  # sometimes nan is a problem here

                series_name = s['name']
                source_data = dict(x=analysis_xscale * xarr[~mask],
                                   y=analysis_yscale * yarr[~mask],
                                   series=(series_name,) * len(xarr[~mask]))

                source = ColumnDataSource(data=source_data)
                # it's a little dirty to add the same value for series for every point
                # but I don't know to a have a second field next to "name", which
                # is used for the subject here

                #
                # Collect data for visibility of the corresponding series
                #
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
                show_symbols = np.count_nonzero(~mask) <= MAX_NUM_POINTS_FOR_SYMBOLS

                legend_entry = subject_display_name + ": " + series_name

                curr_color = subject_colors[subject]
                curr_dash = series_dashes[series_name]
                # curr_symbol = series_symbols[series_name]

                # hover_name = "{} for '{}'".format(series_name, topography_name)
                line_width = LINEWIDTH_FOR_SURFACE_AVERAGE if is_surface_analysis else 1
                topo_alpha = DEFAULT_ALPHA_FOR_TOPOGRAPHIES if is_topography_analysis else 1.
                line_glyph = plot.line('x', 'y', source=source, legend_label=legend_entry,
                                       line_color=curr_color,
                                       line_dash=curr_dash,
                                       line_width=line_width,
                                       line_alpha=topo_alpha,
                                       name=subject_display_name)

                series_glyphs[series_idx].append(line_glyph)

                if show_symbols:
                    symbol_glyph = plot.scatter('x', 'y', source=source,
                                                legend_label=legend_entry,
                                                marker='circle',
                                                size=10,
                                                line_alpha=topo_alpha,
                                                fill_alpha=topo_alpha,
                                                line_color=curr_color,
                                                line_dash=curr_dash,
                                                fill_color=curr_color,
                                                name=subject_display_name)
                    series_glyphs[series_idx].append(symbol_glyph)

                #
                # Prepare JS code to toggle visibility
                #
                # prepare unique id for this line
                glyph_id = f"glyph_{subject_idx}_{series_idx}_line"
                js_args[glyph_id] = line_glyph  # mapping from Python to JS

                # only indices of visible glyphs appear in "active" lists of both button groups
                js_code_toggle_callback += f"{glyph_id}.visible = series_btn_group.active.includes({series_idx}) "
                if is_surface_analysis:
                    js_code_toggle_callback += f"&& surface_btn_group.active.includes({subject_idx});"
                elif is_topography_analysis:
                    js_code_toggle_callback += f"&& topography_btn_group.active.includes({subject_idx - num_surface_subjects});"
                # Opaqueness of topography lines should be changeable
                if is_topography_analysis:
                    js_code_alpha_callback += f"{glyph_id}.glyph.line_alpha = topography_alpha_slider.value;"

                if show_symbols:
                    # prepare unique id for this symbols
                    glyph_id = f"glyph_{subject_idx}_{series_idx}_symbol"
                    js_args[glyph_id] = symbol_glyph  # mapping from Python to JS

                    # only indices of visible glyphs appear in "active" lists of both button groups
                    js_code_toggle_callback += f"{glyph_id}.visible = series_btn_group.active.includes({series_idx}) "
                    if is_surface_analysis:
                        js_code_toggle_callback += f"&& surface_btn_group.active.includes({subject_idx});"
                    elif is_topography_analysis:
                        js_code_toggle_callback += f"&& topography_btn_group.active.includes({subject_idx - num_surface_subjects});"
                        js_code_alpha_callback += f"{glyph_id}.glyph.line_alpha = topography_alpha_slider.value;"
                        js_code_alpha_callback += f"{glyph_id}.glyph.fill_alpha = topography_alpha_slider.value;"

            #
            # Collect special values to be shown in the result card
            #
            if 'scalars' in analysis_result:
                for scalar_name, scalar_dict in analysis.result_obj['scalars'].items():
                    try:
                        scalar_unit = scalar_dict['unit']
                        if scalar_unit == '1':
                            scalar_unit = ''  # we don't want to display '1' as unit
                        special_values.append((subject, scalar_name,
                                               scalar_dict['value'], scalar_unit))
                    except (KeyError, IndexError):
                        _log.warning("Cannot display scalar '%s' given as '%s'. Skipping.", scalar_name, scalar_dict)
                        special_values.append((subject, scalar_name, str(scalar_dict), ''))

            #
            # Collect alert messages from analysis results
            #
            try:
                alerts.extend(analysis_result['alerts'])
            except KeyError:
                pass

        #
        # Adjust visibility of glyphs depending on visibility of series
        #
        for series_idx, glyphs in series_glyphs.items():
            visible = series_idx in series_visible
            for glyph in glyphs:
                glyph.visible = visible

        #
        # Final configuration of the plot
        #

        configure_plot(plot)

        # plot.legend.click_policy = "hide" # can be used to disable lines by clicking on legend
        plot.legend.visible = False  # we have extra widgets to disable lines
        plot.toolbar.active_inspect = None

        #
        # Adding widgets for switching lines on/off
        #
        # ensure a fixed order of the existing series
        series_button_group = CheckboxGroup(
            labels=series_names,
            css_classes=["topobank-series-checkbox"],
            visible=False,
            active=list(series_visible))  # active must be list of ints which are indexes in 'labels'

        # create list of checkbox group, one checkbox group for each subject type
        if has_at_least_one_surface_subject:
            surface_btn_group = CheckboxGroup(
                    labels=subject_checkbox_groups[surface_ct],
                    css_classes=["topobank-subject-checkbox", "topobank-surface-checkbox"],
                    visible=False,
                    active=list(range(len(subject_checkbox_groups[surface_ct]))))  # all indices included -> all active
        else:
            surface_btn_group = Div(visible=False)

        if has_at_least_one_topography_subject:
            topography_btn_group = CheckboxGroup(
                    labels=subject_checkbox_groups[topography_ct],
                    css_classes=["topobank-subject-checkbox", "topobank-topography-checkbox"],
                    visible=False,
                    active=list(range(len(subject_checkbox_groups[topography_ct]))))
        else:
            topography_btn_group = Div(visible=False)

        subject_select_all_btn = Button(label="Select all",
                                        width_policy='min',
                                        visible=False)
        subject_deselect_all_btn = Button(label="Deselect all",
                                          width_policy='min',
                                          visible=False)

        subject_btn_group_toggle_button_label = "Measurements"
        if has_at_least_one_surface_subject:
            subject_btn_group_toggle_button_label = "Average / "+subject_btn_group_toggle_button_label
        subject_btn_group_toggle_button = Toggle(label=subject_btn_group_toggle_button_label,
                                                 button_type='primary')
        series_btn_group_toggle_button = Toggle(label="Data series",
                                                button_type='primary')
        options_group_toggle_button = Toggle(label="Plot options",
                                             button_type='primary')

        topography_alpha_slider = Slider(start=0, end=1, title="Opacity of measurement lines",
                                         value=DEFAULT_ALPHA_FOR_TOPOGRAPHIES
                                         if has_at_least_one_surface_subject else 1.0,
                                         sizing_mode='scale_width',
                                         step=0.1, visible=False)
        options_group = column([topography_alpha_slider])

        #
        # extend mapping of Python to JS objects
        #
        js_args['surface_btn_group'] = surface_btn_group
        js_args['topography_btn_group'] = topography_btn_group
        js_args['subject_select_all_btn'] = subject_select_all_btn
        js_args['subject_deselect_all_btn'] = subject_deselect_all_btn

        js_args['series_btn_group'] = series_button_group
        js_args['topography_alpha_slider'] = topography_alpha_slider

        js_args['subject_btn_group_toggle_btn'] = subject_btn_group_toggle_button
        js_args['series_btn_group_toggle_btn'] = series_btn_group_toggle_button
        js_args['options_group_toggle_btn'] = options_group_toggle_button

        #
        # Toggling visibility of the buttons / checkboxes
        #
        toggle_lines_callback = CustomJS(args=js_args, code=js_code_toggle_callback)
        toggle_subject_checkboxes = CustomJS(args=js_args, code="""
            surface_btn_group.visible = subject_btn_group_toggle_btn.active;
            topography_btn_group.visible = subject_btn_group_toggle_btn.active;
            subject_select_all_btn.visible = subject_btn_group_toggle_btn.active;
            subject_deselect_all_btn.visible = subject_btn_group_toggle_btn.active;
        """)
        toggle_series_checkboxes = CustomJS(args=js_args, code="""
            series_btn_group.visible = series_btn_group_toggle_btn.active;
        """)
        toggle_options = CustomJS(args=js_args, code="""
            topography_alpha_slider.visible = options_group_toggle_btn.active;
        """)

        subject_btn_groups = layout([subject_select_all_btn, subject_deselect_all_btn],
                                    [surface_btn_group],
                                    [topography_btn_group])

        series_button_group.js_on_click(toggle_lines_callback)
        if has_at_least_one_surface_subject:
            surface_btn_group.js_on_click(toggle_lines_callback)
        topography_btn_group.js_on_click(toggle_lines_callback)
        subject_btn_group_toggle_button.js_on_click(toggle_subject_checkboxes)
        series_btn_group_toggle_button.js_on_click(toggle_series_checkboxes)
        options_group_toggle_button.js_on_click(toggle_options)

        #
        # Callback for changing opaqueness of measurement lines
        #
        topography_alpha_slider.js_on_change('value', CustomJS(args=js_args,
                                                               code=js_code_alpha_callback))

        #
        # Callback for toggling lines
        #
        subject_select_all_btn.js_on_click(CustomJS(args=js_args, code="""
            let all_topo_idx = [];
            for (let i=0; i<topography_btn_group.labels.length; i++) {
                all_topo_idx.push(i);
            }
            topography_btn_group.active = all_topo_idx;

            /** surface_btn_group may just be a div if no averages defined */
            if ('labels' in surface_btn_group) {
                let all_surf_idx = [];
                for (let i=0; i<surface_btn_group.labels.length; i++) {
                    all_surf_idx.push(i);
                }
                surface_btn_group.active = all_surf_idx;
            }
        """))
        subject_deselect_all_btn.js_on_click(CustomJS(args=js_args, code="""
            surface_btn_group.active = [];
            topography_btn_group.active = [];
        """))
        #
        # Build layout for buttons underneath plot
        #
        widgets = grid([
            [subject_btn_group_toggle_button, series_btn_group_toggle_button, options_group_toggle_button],
            [subject_btn_groups, series_button_group, options_group],
        ])

        #
        # Convert plot and widgets to HTML, add meta data for template
        #
        script, div = components(column(plot, widgets, sizing_mode='scale_width'))

        context.update(dict(
            plot_script=script,
            plot_div=div,
            special_values=special_values,
            extra_warnings=alerts,
            topography_colors=json.dumps(list(subject_colors.values())),
            series_dashes=json.dumps(list(series_dashes.values()))))

        return context


class PowerSpectrumCardView(PlotCardView):
    pass


class ContactMechanicsCardView(SimpleCardView):

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        analyses_success = context['analyses_success']

        if len(analyses_success) == 0:
            #
            # Prepare plot, controls, and table with special values..
            #
            context.update(
                dict(plot_script="",
                     plot_div="No successfully finished analyses available")
            )
        else:

            #
            # Prepare helper variables
            #
            color_cycle = itertools.cycle(Category10[10])
            topography_colors = OrderedDict()  # key: Topography instance
            topography_names = []
            js_code = ""
            js_args = {}

            #
            # Generate two plots in two tabs based on same data sources
            #
            sources = []
            labels = []
            for analysis in analyses_success:
                analysis_result = analysis.result_obj
                # subject is always a topography for contact analyses so far,
                # so there is a surface
                surface = analysis.subject.surface
                data = dict(
                    topography_name=(analysis.subject.name,) * len(analysis_result['mean_pressures']),
                    surface_name=(surface.name,) * len(analysis_result['mean_pressures']),
                    mean_pressure=analysis_result['mean_pressures'],
                    total_contact_area=analysis_result['total_contact_areas'],
                    mean_displacement=analysis_result['mean_displacements'],
                    mean_gap=analysis_result['mean_gaps'],
                    fill_alpha=[1 if c else 0.3 for c in analysis_result['converged']],
                    converged_info=["yes" if c else "no" for c in analysis_result['converged']],
                    data_path=analysis_result['data_paths'])

                # the name of the data source is used in javascript in
                # order to find out the analysis id
                source = ColumnDataSource(data, name="analysis-{}".format(analysis.id))

                sources.append(source)
                labels.append(analysis.subject.name)

                #
                # find out colors for topographies
                #
                if analysis.subject not in topography_colors:
                    topography_colors[analysis.subject] = next(color_cycle)
                    topography_names.append(analysis.subject.name)

            load_axis_label = "Normalized pressure p/E*"
            area_axis_label = "Fractional contact area A/A0"
            disp_axis_label = "Normalized mean gap u/h_rms"

            color_cycle = itertools.cycle(Category10[10])

            select_callback = CustomJS(args=dict(sources=sources), code="selection_handler(cb_obj, cb_data, sources);")
            tap = TapTool(behavior='select', callback=select_callback)

            #
            # Configure tooltips
            #
            tooltips = [
                ("topography", "@topography_name"),
                ("surface", "@surface_name"),
                (load_axis_label, "@mean_pressure"),
                (area_axis_label, "@total_contact_area"),
                (disp_axis_label, "@mean_gap"),
                ("properly converged", "@converged_info")
            ]
            hover = HoverTool(tooltips=tooltips)

            tools = ["pan", "reset", "save", "wheel_zoom", "box_zoom", tap, hover]

            contact_area_plot = figure(title=None,
                                       plot_height=400,
                                       sizing_mode='scale_width',
                                       x_axis_label=load_axis_label,
                                       y_axis_label=area_axis_label,
                                       x_axis_type="log",
                                       y_axis_type="log",
                                       tools=tools)

            load_plot = figure(title=None,
                               plot_height=400,
                               sizing_mode='scale_width',
                               x_axis_label=disp_axis_label,
                               y_axis_label=load_axis_label,
                               x_axis_type="linear",
                               y_axis_type="log", tools=tools)

            for source, label in zip(sources, labels):
                curr_color = next(color_cycle)
                r1 = contact_area_plot.circle('mean_pressure', 'total_contact_area',
                                              source=source,
                                              fill_alpha='fill_alpha',  # to indicate if converged or not
                                              fill_color=curr_color,
                                              line_color=None,
                                              size=12)
                r2 = load_plot.circle('mean_gap', 'mean_pressure',
                                      source=source,
                                      fill_alpha='fill_alpha',  # to indicate if converged or not
                                      fill_color=curr_color,
                                      line_color=None,
                                      size=12)

                selected_circle = Circle(fill_alpha='fill_alpha', fill_color=curr_color,
                                         line_color="black", line_width=4)
                nonselected_circle = Circle(fill_alpha='fill_alpha', fill_color=curr_color,
                                            line_color=None)

                for renderer in [r1, r2]:
                    renderer.selection_glyph = selected_circle
                    renderer.nonselection_glyph = nonselected_circle

                #
                # Prepare JS code to toggle visibility
                #
                topography_idx = topography_names.index(label)

                # prepare unique ids for this symbols (one for each plot)
                glyph_id_area_plot = f"glyph_{topography_idx}_area_symbol"
                glyph_id_load_plot = f"glyph_{topography_idx}_load_symbol"
                js_args[glyph_id_area_plot] = r1  # mapping from Python to JS
                js_args[glyph_id_load_plot] = r2  # mapping from Python to JS

                # only indices of visible glyphs appear in "active" lists of both button groups
                js_code += f"{glyph_id_area_plot}.visible = topography_btn_group.active.includes({topography_idx});"
                js_code += f"{glyph_id_load_plot}.visible = topography_btn_group.active.includes({topography_idx});"

            configure_plot(contact_area_plot)
            configure_plot(load_plot)

            #
            # Adding widgets for switching symbols on/off
            #
            topography_button_group = CheckboxGroup(
                labels=topography_names,
                css_classes=["topobank-subject-checkbox"],
                visible=False,
                active=list(range(len(topography_names))))  # all active

            topography_btn_group_toggle_button = Toggle(label="Measurements", button_type='primary')

            subject_select_all_btn = Button(label="Select all",
                                            width_policy='min',
                                            visible=False)
            subject_deselect_all_btn = Button(label="Deselect all",
                                              width_policy='min',
                                              visible=False)

            # extend mapping of Python to JS objects
            js_args['topography_btn_group'] = topography_button_group
            js_args['topography_btn_group_toggle_btn'] = topography_btn_group_toggle_button
            js_args['subject_select_all_btn'] = subject_select_all_btn
            js_args['subject_deselect_all_btn'] = subject_deselect_all_btn

            toggle_lines_callback = CustomJS(args=js_args, code=js_code)
            toggle_topography_checkboxes = CustomJS(args=js_args, code="""
                topography_btn_group.visible = topography_btn_group_toggle_btn.active;
                subject_select_all_btn.visible = topography_btn_group_toggle_btn.active;
                subject_deselect_all_btn.visible = topography_btn_group_toggle_btn.active;
            """)

            widgets = grid([
                [topography_btn_group_toggle_button],
                layout([subject_select_all_btn, subject_deselect_all_btn],
                       [topography_button_group])
            ])
            topography_button_group.js_on_click(toggle_lines_callback)
            topography_btn_group_toggle_button.js_on_click(toggle_topography_checkboxes)

            #
            # Callback for toggling lines
            #
            subject_select_all_btn.js_on_click(CustomJS(args=js_args, code="""
                let all_topo_idx = [];
                for (let i=0; i<topography_btn_group.labels.length; i++) {
                    all_topo_idx.push(i);
                }
                topography_btn_group.active = all_topo_idx;
            """))
            subject_deselect_all_btn.js_on_click(CustomJS(args=js_args, code="""
                topography_btn_group.active = [];
            """))

            #
            # Layout plot
            #
            contact_area_tab = Panel(child=contact_area_plot, title="Contact area versus load")
            load_tab = Panel(child=load_plot, title="Load versus displacement")

            tabs = Tabs(tabs=[contact_area_tab, load_tab])
            col = column(tabs, widgets, sizing_mode='scale_width')

            plot_script, plot_div = components(col)

            context.update(plot_script=plot_script, plot_div=plot_div)

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

        context['extra_warnings'] = [
            dict(alert_class='alert-warning',
                 message="""
                 Translucent data points did not converge within iteration limit and may carry large errors.
                 <i>A</i> is the true contact area and <i>A0</i> the apparent contact area,
                 i.e. the size of the provided measurement.""")
        ]

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
                v = round_to_significant_digits(v.astype(float),
                                                NUM_SIGNIFICANT_DIGITS_RMS_VALUES)
        return v

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        analyses_success = context['analyses_success']

        data = []
        for analysis in analyses_success:
            analysis_result = analysis.result_obj

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
               toolbar_location="above")

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
        colorbar.formatter = FuncTickFormatter(code="return format_exponential(tick);")
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
               toolbar_location="above")

    p.step(edges[:-1], hist, mode="before", line_width=2)

    configure_plot(p)

    return p


def contact_mechanics_data(request):
    """Loads extra data for an analysis card

    :param request:
    :return:
    """
    if not request.is_ajax():
        raise Http404

    request_method = request.POST
    user = request.user

    try:
        analysis_id = int(request_method.get('analysis_id'))
        index = int(request_method.get('index'))
    except (KeyError, ValueError, TypeError):
        return JsonResponse({'error': 'error in request data'}, status=400)

    #
    # Interpret given arguments
    #
    analysis = Analysis.objects.get(id=analysis_id)

    unit = analysis.subject.unit

    if user.has_perm('view_surface', analysis.related_surface):

        #
        # Try to get results from cache
        #
        cache_key = "contact-mechanics-plots-json-analysis-{}-index-{}".format(analysis.id, index)
        plots_json = cache.get(cache_key)
        if plots_json is None:

            #
            # generate plots and save in cache
            #

            pressure_tol = 0  # tolerance for deciding whether point is in contact
            gap_tol = 0  # tolerance for deciding whether point is in contact
            # min_pentol = 1e-12 # lower bound for the penetration tolerance

            #
            # Here we assume a special format for the analysis results
            #
            data_path = analysis.result_obj['data_paths'][index]

            data = default_storage.open(data_path)
            ds = xr.load_dataset(data.open(mode='rb'), engine="h5netcdf")
            # "engine" argument needed after version updates for TopoBank 0.15.0

            pressure = ds['pressure'].values
            contacting_points = ds['contacting_points'].values
            displacement = ds['displacement'].values
            gap = ds['gap'].values

            # gap, displacement

            #
            # calculate contact areas
            #

            patch_ids = assign_patch_numbers(contacting_points)[1]
            contact_areas = patch_areas(patch_ids) * analysis.result_obj['area_per_pt']

            #
            # Common figure parameters
            #

            topo = analysis.subject
            aspect_ratio = topo.size_x / topo.size_y
            frame_height = 500
            frame_width = int(frame_height * aspect_ratio)

            MAX_FRAME_WIDTH = 550

            if frame_width > MAX_FRAME_WIDTH:  # rule of thumb, scale down if too wide
                frame_width = MAX_FRAME_WIDTH
                frame_height = int(frame_width / aspect_ratio)

            common_kwargs = dict(frame_width=frame_width,
                                 frame_height=frame_height)

            geometry_figure_common_args = common_kwargs.copy()
            geometry_figure_common_args.update(topo_unit=topo.unit, topo_size=(topo.size_x, topo.size_y))

            plots = {
                #
                #  Geometry figures
                #
                'contact-geometry': _contact_mechanics_geometry_figure(
                    contacting_points,
                    colorbar_title="Contact geometry",
                    **geometry_figure_common_args),
                'contact-pressure': _contact_mechanics_geometry_figure(
                    pressure,
                    colorbar_title=r'Pressure',
                    value_unit='E*',
                    **geometry_figure_common_args),
                'displacement': _contact_mechanics_geometry_figure(
                    displacement,
                    colorbar_title=r'Displacem.',
                    value_unit=unit,
                    **geometry_figure_common_args),
                'gap': _contact_mechanics_geometry_figure(
                    gap,
                    colorbar_title=r'Gap',
                    value_unit=unit,
                    **geometry_figure_common_args),
                #
                # Distribution figures
                #
                'pressure-distribution': _contact_mechanics_distribution_figure(
                    pressure[contacting_points],
                    x_axis_label="Pressure p (E*)",
                    y_axis_label="Probability P(p) (1/E*)",
                    **common_kwargs),
                'gap-distribution': _contact_mechanics_distribution_figure(
                    gap[gap > gap_tol],
                    x_axis_label="Gap g ({})".format(topo.unit),
                    y_axis_label="Probability P(g) (1/{})".format(topo.unit),
                    **common_kwargs),
                'cluster-size-distribution': _contact_mechanics_distribution_figure(
                    contact_areas,
                    x_axis_label="Cluster area A({}²)".format(topo.unit),
                    y_axis_label="Probability P(A)",
                    x_axis_type="log",
                    y_axis_type="log",
                    **common_kwargs),
            }

            plots_json = {pn: json.dumps(json_item(plots[pn])) for pn in plots}
            cache.set(cache_key, plots_json)
        else:
            _log.debug("Using plots from cache.")

        return JsonResponse(plots_json, status=200)
    else:
        return JsonResponse({}, status=403)


def contact_mechanics_dzi(request, pk, index, quantity, dzi_filename):
    try:
        pk = int(pk)
    except ValueError:
        raise Http404()

    try:
        index = int(index)
    except ValueError:
        raise Http404()

    analysis = Analysis.objects.get(id=pk)

    if not request.user.has_perm('view_surface', analysis.related_surface):
        raise PermissionDenied()

    # okay, we have a valid topography and the user is allowed to see it

    data_path = analysis.result_obj['data_paths'][index]
    name = f'{data_path}-{quantity}-{dzi_filename}'
    url = default_storage.url(name)
    _log.info(url)
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

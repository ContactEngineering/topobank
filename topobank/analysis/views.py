import pickle
import json
from typing import Optional, Dict, Any

import numpy as np
import math
import itertools
from collections import OrderedDict

from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse, Http404, JsonResponse
from django.views.generic import DetailView, FormView, TemplateView
from django.urls import reverse_lazy
from django.db.models import Q
from django import template
from django.core.files.storage import default_storage
from django.core.cache import cache  # default cache
from django.core.exceptions import PermissionDenied
from django.shortcuts import reverse
from django.conf import settings

import django_tables2 as tables

from bokeh.layouts import row, column, grid
from bokeh.models import ColumnDataSource, CustomJS, TapTool, Circle, HoverTool
from bokeh.palettes import Category10
from bokeh.models.formatters import FuncTickFormatter
from bokeh.models.ranges import DataRange1d
from bokeh.plotting import figure
from bokeh.embed import components, json_item
from bokeh.models.widgets import CheckboxGroup, Tabs, Panel, Toggle
from bokeh.models.widgets.markups import Paragraph
from bokeh.models import Legend, LinearColorMapper, ColorBar, CategoricalColorMapper

import xarray as xr

from pint import UnitRegistry, UndefinedUnitError

from guardian.shortcuts import get_objects_for_user, get_anonymous_user

from trackstats.models import Metric

from ContactMechanics.Tools.ContactAreaAnalysis import patch_areas, assign_patch_numbers

from ..manager.models import Topography, Surface
from ..manager.utils import selected_instances, instances_to_selection, instances_to_topographies, \
    selection_to_subjects_json, subjects_from_json, subjects_to_json
from ..usage_stats.utils import increase_statistics_by_date_and_object
from .models import Analysis, AnalysisFunction, AnalysisCollection, CARD_VIEW_FLAVORS, ImplementationMissingException
from .forms import FunctionSelectForm
from .utils import get_latest_analyses, round_to_significant_digits, request_analysis

import logging

_log = logging.getLogger(__name__)

SMALLEST_ABSOLUT_NUMBER_IN_LOGPLOTS = 1e-100
MAX_NUM_POINTS_FOR_SYMBOLS = 50
NUM_SIGNIFICANT_DIGITS_RMS_VALUES = 5


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

        if len(analyses_success) == 0:
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

        first_analysis_result = analyses_success[0].result_obj
        title = first_analysis_result['name']

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
        plot = figure(title=title,
                      plot_height=300,
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
            ("topography", "$name"),
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
        subject_names = []

        series_dashes = OrderedDict()  # key: series name
        series_names = []

        # Also give each series a symbol (only used for small number of points)
        # series_symbols = OrderedDict()  # key: series name

        #
        # Traverse analyses and plot lines
        #
        js_code = ""
        js_args = {}

        special_values = []  # elements: tuple(subject, quantity name, value, unit string)

        for analysis in analyses_success:

            subject = analysis.subject
            subject_name = subject.name

            #
            # find out colors for subject
            #
            if subject not in subject_colors:
                subject_colors[subject] = next(color_cycle)
                subject_names.append(subject_name)

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
                if get_axis_type('yscale') == 'log':
                    mask |= np.isclose(yarr, 0, atol=SMALLEST_ABSOLUT_NUMBER_IN_LOGPLOTS)

                series_name = s['name']

                source = ColumnDataSource(data=dict(x=analysis_xscale * xarr[~mask],
                                                    y=analysis_yscale * yarr[~mask],
                                                    series=(series_name,) * len(xarr)))
                # it's a little dirty to add the same value for series for every point
                # but I don't know to a have a second field next to "name", which
                # is used for the topography here

                #
                # find out dashes for data series
                #
                if series_name not in series_dashes:
                    series_dashes[series_name] = next(dash_cycle)
                    # series_symbols[series_name] = next(symbol_cycle)
                    series_names.append(series_name)

                #
                # Actually plot the line
                #
                show_symbols = np.count_nonzero(~mask) <= MAX_NUM_POINTS_FOR_SYMBOLS

                legend_entry = subject_name + ": " + series_name

                curr_color = subject_colors[subject]
                curr_dash = series_dashes[series_name]
                # curr_symbol = series_symbols[series_name]

                # hover_name = "{} for '{}'".format(series_name, topography_name)

                line_glyph = plot.line('x', 'y', source=source, legend_label=legend_entry,
                                       line_color=curr_color,
                                       line_dash=curr_dash, name=subject_name)
                if show_symbols:
                    symbol_glyph = plot.scatter('x', 'y', source=source,
                                                legend_label=legend_entry,
                                                marker='circle',
                                                size=10,
                                                line_color=curr_color,
                                                line_dash=curr_dash,
                                                fill_color=curr_color,
                                                name=subject_name)

                #
                # Prepare JS code to toggle visibility
                #
                series_idx = series_names.index(series_name)
                subject_idx = subject_names.index(subject_name)  # TODO be careful, may not be unique

                # prepare unique id for this line
                glyph_id = f"glyph_{subject_idx}_{series_idx}_line"
                js_args[glyph_id] = line_glyph  # mapping from Python to JS

                # only indices of visible glyphs appear in "active" lists of both button groups
                js_code += f"{glyph_id}.visible = series_btn_group.active.includes({series_idx}) " \
                           + f"&& topography_btn_group.active.includes({subject_idx});"
                # TODO rename topopgraphy_btn_group

                if show_symbols:
                    # prepare unique id for this symbols
                    glyph_id = f"glyph_{subject_idx}_{series_idx}_symbol"
                    js_args[glyph_id] = symbol_glyph  # mapping from Python to JS

                    # only indices of visible glyphs appear in "active" lists of both button groups
                    js_code += f"{glyph_id}.visible = series_btn_group.active.includes({series_idx}) " \
                               + f"&& topography_btn_group.active.includes({subject_idx});"

            #
            # Collect special values to be shown in the result card
            #
            if 'scalars' in analysis.result_obj:
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
        # Final configuration of the plot
        #

        # plot.legend.click_policy = "hide" # can be used to disable lines by clicking on legend
        plot.legend.visible = False  # we have extra widgets to disable lines
        plot.toolbar.logo = None
        plot.toolbar.active_inspect = None
        plot.xaxis.axis_label_text_font_style = "normal"
        plot.yaxis.axis_label_text_font_style = "normal"
        plot.xaxis.major_label_text_font_size = "12pt"
        plot.yaxis.major_label_text_font_size = "12pt"

        # see js function "format_exponential()" in project.js file
        plot.xaxis.formatter = FuncTickFormatter(code="return format_exponential(tick);")
        plot.yaxis.formatter = FuncTickFormatter(code="return format_exponential(tick);")

        #
        # Adding widgets for switching lines on/off
        #
        series_button_group = CheckboxGroup(
            labels=series_names,
            css_classes=["topobank-series-checkbox"],
            visible=False,
            active=list(range(len(series_names))))  # all active

        subject_names_for_btn_group = list(s.name for s in subject_colors.keys())
        topography_button_group = CheckboxGroup(
            labels=subject_names_for_btn_group,
            css_classes=["topobank-topography-checkbox"],
            visible=False,
            active=list(range(len(subject_names_for_btn_group))))  # all active

        topography_btn_group_toggle_button = Toggle(label="Topographies")
        series_btn_group_toggle_button = Toggle(label="Data Series")

        # extend mapping of Python to JS objects
        js_args['series_btn_group'] = series_button_group
        js_args['topography_btn_group'] = topography_button_group
        js_args['topography_btn_group_toggle_btn'] = topography_btn_group_toggle_button
        js_args['series_btn_group_toggle_btn'] = series_btn_group_toggle_button

        # add code for setting styles of widgetbox elements
        # js_code += """
        # style_checkbox_labels({});
        # """.format(card_id)

        toggle_lines_callback = CustomJS(args=js_args, code=js_code)
        toggle_topography_checkboxes = CustomJS(args=js_args, code="""
            topography_btn_group.visible = topography_btn_group_toggle_btn.active;
        """)
        toggle_series_checkboxes = CustomJS(args=js_args, code="""
            series_btn_group.visible = series_btn_group_toggle_btn.active;
        """)

        #
        # TODO Idea: Generate DIVs with Markup of colors and dashes and align with Buttons/Checkboxes
        #

        widgets = grid([
            [topography_btn_group_toggle_button, series_btn_group_toggle_button],
            [topography_button_group, series_button_group]
        ])

        series_button_group.js_on_click(toggle_lines_callback)
        topography_button_group.js_on_click(toggle_lines_callback)
        topography_btn_group_toggle_button.js_on_click(toggle_topography_checkboxes)
        series_btn_group_toggle_button.js_on_click(toggle_series_checkboxes)
        #
        # Convert plot and widgets to HTML, add meta data for template
        #
        script, div = components(column(plot, widgets, sizing_mode='scale_width'))

        context.update(dict(
            plot_script=script,
            plot_div=div,
            special_values=special_values,
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

                data = dict(
                    topography_name=(analysis.subject.name,) * len(analysis_result['mean_pressures']),
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

            contact_area_plot.xaxis.formatter = FuncTickFormatter(code="return format_exponential(tick);")
            contact_area_plot.yaxis.formatter = FuncTickFormatter(code="return format_exponential(tick);")

            load_plot = figure(title=None,
                               plot_height=400,
                               sizing_mode='scale_width',
                               x_axis_label=disp_axis_label,
                               y_axis_label=load_axis_label,
                               x_axis_type="linear",
                               y_axis_type="log", tools=tools)

            load_plot.yaxis.formatter = FuncTickFormatter(code="return format_exponential(tick);")

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

            _configure_plot(contact_area_plot)
            _configure_plot(load_plot)

            #
            # Adding widget for switching symbols on/off
            #
            topography_button_group = CheckboxGroup(
                labels=topography_names,
                css_classes=["topobank-topography-checkbox"],
                visible=False,
                active=list(range(len(topography_names))))  # all active

            topography_btn_group_toggle_button = Toggle(label="Topographies")

            # extend mapping of Python to JS objects
            js_args['topography_btn_group'] = topography_button_group
            js_args['topography_btn_group_toggle_btn'] = topography_btn_group_toggle_button

            toggle_lines_callback = CustomJS(args=js_args, code=js_code)
            toggle_topography_checkboxes = CustomJS(args=js_args, code="""
                        topography_btn_group.visible = topography_btn_group_toggle_btn.active;
                    """)

            widgets = grid([
                [topography_btn_group_toggle_button],
                [topography_button_group]
            ])
            topography_button_group.js_on_click(toggle_lines_callback)
            topography_btn_group_toggle_button.js_on_click(toggle_topography_checkboxes)

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
        unique_kwargs = context['unique_kwargs'][topography_ct]
        if unique_kwargs:
            initial_calc_kwargs = unique_kwargs
        else:
            # default initial arguments for form if we don't have unique common arguments
            contact_mechanics_func = AnalysisFunction.objects.get(name="Contact Mechanics")
            initial_calc_kwargs = contact_mechanics_func.get_default_kwargs()
            initial_calc_kwargs['substrate_str'] = 'nonperiodic'  # because most topographies are non-periodic

        context['initial_calc_kwargs'] = initial_calc_kwargs

        context['extra_warnings'] = [
            dict(alert_class='alert-warning',
                 message="""
                 Translucent data points did not converge within iteration limit and may carry large errors.
                 <i>A</i> is the true contact area and <i>A0</i> the apparent contact area,
                 i.e. the size of the provided topography.""")
        ]

        context['limits_calc_kwargs'] = settings.CONTACT_MECHANICS_KWARGS_LIMITS

        return context


class RMSTable(tables.Table):
    topography = tables.Column(linkify=lambda **kwargs: kwargs['record']['topography'].get_absolute_url(),
                               accessor='topography__name')
    quantity = tables.Column()
    direction = tables.Column()
    value = tables.Column()
    unit = tables.Column()


class RmsTableCardView(SimpleCardView):

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        analyses_success = context['analyses_success']

        data = []
        for analysis in analyses_success:
            analysis_result = analysis.result_obj

            for d in analysis_result:
                if math.isnan(d['value']):
                    d['value'] = None  # will be interpreted as null in JS, replace there with NaN!
                    # It's not easy to pass NaN as JSON:
                    # https://stackoverflow.com/questions/15228651/how-to-parse-json-string-containing-nan-in-node-js
                else:
                    # convert float32 to float, round to fixed number of significant digits
                    d['value'] = round_to_significant_digits(d['value'].astype(float),
                                                             NUM_SIGNIFICANT_DIGITS_RMS_VALUES)

                if not d['direction']:
                    d['direction'] = ''
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
        # table = RMSTable(data=data, empty_text="No RMS values calculated.", request=self.request)

        context.update(dict(
            table_data=data
        ))

        return context


def _configure_plot(plot):
    plot.toolbar.logo = None
    plot.xaxis.axis_label_text_font_style = "normal"
    plot.yaxis.axis_label_text_font_style = "normal"
    plot.xaxis.major_label_text_font_size = "12pt"
    plot.yaxis.major_label_text_font_size = "12pt"


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


def _contact_mechanics_geometry_figure(values, frame_width, frame_height, topo_unit, topo_size, title=None,
                                       value_unit=None):
    """

    :param values: 2D numpy array
    :param frame_width:
    :param frame_height:
    :param topo_unit:
    :param topo_size:
    :param title:
    :param value_unit:
    :return:
    """

    x_range = DataRange1d(start=0, end=topo_size[0], bounds='auto', range_padding=5)
    y_range = DataRange1d(start=0, end=topo_size[1], bounds='auto', range_padding=5)

    p = figure(title=title,
               x_range=x_range,
               y_range=y_range,
               frame_width=frame_width,
               frame_height=frame_height,
               x_axis_label="Position x ({})".format(topo_unit),
               y_axis_label="Position y ({})".format(topo_unit),
               match_aspect=True,
               toolbar_location="above")

    boolean_values = values.dtype == np.bool

    if boolean_values:
        color_mapper = LinearColorMapper(palette=["black", "white"], low=0, high=1)
    else:
        min_val = values.min()
        max_val = values.max()

        color_mapper = LinearColorMapper(palette='Viridis256', low=min_val, high=max_val)

    p.image([values], x=0, y=0, dw=topo_size[0], dh=topo_size[1], color_mapper=color_mapper)

    if not boolean_values:
        colorbar = ColorBar(color_mapper=color_mapper,
                            label_standoff=12,
                            location=(0, 0),
                            title=value_unit)

        p.add_layout(colorbar, "right")

    _configure_plot(p)

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

    if x_axis_type == "log":
        p.xaxis.formatter = FuncTickFormatter(code="return format_exponential(tick);")
    if y_axis_type == "log":
        p.yaxis.formatter = FuncTickFormatter(code="return format_exponential(tick);")

    p.step(edges[:-1], hist, mode="before", line_width=2)

    _configure_plot(p)

    return p


def _contact_mechanics_displacement_figure():
    pass


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
            ds = xr.load_dataset(data.open(mode='rb'))

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
                    title="Contact geometry",
                    **geometry_figure_common_args),
                'contact-pressure': _contact_mechanics_geometry_figure(
                    pressure,
                    title=r'Contact pressure p(E*)',
                    **geometry_figure_common_args),
                'displacement': _contact_mechanics_geometry_figure(
                    displacement,
                    title=r'Displacement', value_unit=unit,
                    **geometry_figure_common_args),
                'gap': _contact_mechanics_geometry_figure(
                    gap, title=r'Gap', value_unit=unit,
                    **geometry_figure_common_args),
                #
                # Distribution figures
                #
                'pressure-distribution': _contact_mechanics_distribution_figure(
                    pressure[contacting_points],
                    title="Pressure distribution",
                    x_axis_label="Pressure p (E*)",
                    y_axis_label="Probability P(p) (1/E*)",
                    **common_kwargs),
                'gap-distribution': _contact_mechanics_distribution_figure(
                    gap[gap > gap_tol],
                    title="Gap distribution",
                    x_axis_label="Gap g ({})".format(topo.unit),
                    y_axis_label="Probability P(g) (1/{})".format(topo.unit),
                    **common_kwargs),
                'cluster-size-distribution': _contact_mechanics_distribution_figure(
                    contact_areas,
                    title="Cluster size distribution",
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
                'icon': "diamond",
                'href': reverse('manager:surface-detail', kwargs=dict(pk=topo.surface.pk)),
                'active': False,
                'login_required': False,
                'tooltip': f"Properties of surface '{topo.surface.label}'",
            },
            {
                'title': f"{topo.name}",
                'icon': "file-o",
                'href': reverse('manager:topography-detail', kwargs=dict(pk=topo.pk)),
                'active': False,
                'login_required': False,
                'tooltip': f"Properties of topography '{topo.name}'",
            }
        ])
    elif len(surfaces) == 1 and all(t.surface == surfaces[0] for t in topographies):
        # exactly one surface was selected -> show also tab of surface
        surface = surfaces[0]
        tabs.append(
            {
                'title': f"{surface.label}",
                'icon': "diamond",
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
                'icon': "area-chart",
                'href': reverse('analysis:list'),
                'active': False,
                'login_required': False,
                'tooltip': "Results for selected analysis functions",
            },
            {
                'title': f"{function.name}",
                'icon': "area-chart",
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
                'icon': "area-chart",
                'href': self.request.path,
                'active': True,
                'login_required': False,
                'tooltip': "Results for selected analysis functions",
                'show_basket': True,
            }
        )
        context['extra_tabs'] = tabs

        return context

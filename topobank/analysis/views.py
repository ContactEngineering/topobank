import io
import pickle
import json
import numpy as np
import itertools
from collections import OrderedDict
from io import BytesIO
import zipfile
import os.path

from django.http import HttpResponse, HttpResponseForbidden, Http404, JsonResponse, HttpResponseBadRequest
from django.views.generic import DetailView, FormView, TemplateView
from django.urls import reverse_lazy
from django.db.models import Q
from django.conf import settings
from django import template
from rest_framework.generics import RetrieveAPIView
from django.core.files.storage import default_storage
from django.core.cache import cache  # default cache
from django.core.exceptions import PermissionDenied
from django.shortcuts import reverse

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
import pandas as pd

from pint import UnitRegistry, UndefinedUnitError

from guardian.shortcuts import get_objects_for_user, get_anonymous_user

from trackstats.models import Metric

from ContactMechanics.Tools.ContactAreaAnalysis import patch_areas, assign_patch_numbers
import SurfaceTopography, ContactMechanics, muFFT, NuMPI

from ..manager.models import Topography, Surface
from ..manager.utils import selected_instances, instances_to_selection, current_selection_as_basket_items, instances_to_topographies
from ..usage_stats.utils import increase_statistics_by_date_and_object
from .models import Analysis, AnalysisFunction, AnalysisCollection
from .serializers import AnalysisSerializer
from .forms import FunctionSelectForm
from .utils import get_latest_analyses, mangle_sheet_name
from .functions import CONTACT_MECHANICS_KWARGS_LIMITS, contact_mechanics
from topobank.analysis.utils import request_analysis

import logging

_log = logging.getLogger(__name__)

SMALLEST_ABSOLUT_NUMBER_IN_LOGPLOTS = 1e-100
MAX_NUM_POINTS_FOR_SYMBOLS = 50

CARD_VIEW_FLAVORS = ['simple', 'plot', 'power spectrum', 'contact mechanics']


def card_view_class(card_view_flavor):
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
    GET parameters.

    :param request:
    :return: HTTPResponse
    """
    if not request.is_ajax():
        return Http404

    try:
        function_id = int(request.GET.get('function_id'))
    except (KeyError, ValueError, TypeError):
        return HttpResponse("Error in GET arguments")

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
            template_flavor = self.request.GET.get('template_flavor')
        except (KeyError, ValueError):
            raise ValueError("Cannot read 'template_flavor' from GET arguments.")

        if template_flavor is None:
            raise ValueError("Missing 'template_flavor' in GET arguments.")

        template_name = self._template_name(self.__class__.__name__, template_flavor)

        #
        # If template does not exist, return template from parent class
        #
        # MAYBE later: go down the hierachy and take first template found
        try:
            template.loader.get_template(template_name)
        except template.TemplateDoesNotExist:
            base_class = self.__class__.__bases__[0]
            template_name = self._template_name(base_class.__name__, template_flavor)

        return [template_name]

    def get_context_data(self, **kwargs):
        """

        Gets function ids and topography ids from GET parameters.


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
          topographies_missing: list of topographies for which there is no Analysis object yet
          topography_ids_requested_json: json representation of list with all requested topography ids
        """
        context = super().get_context_data(**kwargs)

        request = self.request
        request_method = request.GET
        user = request.user

        try:
            function_id = int(request_method.get('function_id'))
            card_id = request_method.get('card_id')
            topography_ids = [int(tid) for tid in request_method.getlist('topography_ids[]')]
        except (KeyError, ValueError):
            return HttpResponse("Error in GET arguments")

        #
        # Get all relevant analysis objects for this function and topography ids
        #
        analyses_avail = get_latest_analyses(user, function_id, topography_ids)

        #
        # Filter for analyses where the user has read permission for the related surface
        #
        readable_surfaces = get_objects_for_user(user, ['view_surface'], klass=Surface)
        analyses_avail = analyses_avail.filter(topography__surface__in=readable_surfaces)

        #
        # collect list of topographies for which no analyses exist
        #
        topographies_available_ids = [a.topography.id for a in analyses_avail]
        topographies_missing = []
        for tid in topography_ids:
            if tid not in topographies_available_ids:
                try:
                    topo = Topography.objects.get(id=tid)
                    topographies_missing.append(topo)
                except Topography.DoesNotExist:
                    # topography may be deleted in between
                    pass

        #
        # collect all keyword arguments and check whether they are equal
        #
        unique_kwargs = None  # means: there are differences or no analyses available
        for av in analyses_avail:
            kwargs = pickle.loads(av.kwargs)
            if unique_kwargs is None:
                unique_kwargs = kwargs
            elif kwargs != unique_kwargs:
                unique_kwargs = None
                break

        function = AnalysisFunction.objects.get(id=function_id)

        #
        # automatically trigger analyses for missing topographies
        #
        kwargs_for_missing = unique_kwargs or {}
        topographies_triggered = []
        for topo in topographies_missing:
            if user.has_perm('view_surface', topo.surface):
                triggered_analysis = request_analysis(user, function, topo, **kwargs_for_missing)
                topographies_triggered.append(topo)
                topographies_available_ids.append(topo.id)
                _log.info(f"Triggered analysis {triggered_analysis.id} for function {function.name} "+\
                          f"and topography {topo.id}.")
        topographies_missing = [ t for t in topographies_missing if t not in topographies_triggered]

        # now all topographies which needed to be triggered, should have been triggered
        # with common arguments if possible
        # collect information about available analyses again
        if len(topographies_triggered) > 0:

            # if no analyses where available before, unique_kwargs is None
            # which is interpreted as "differing arguments". This is wrong
            # in that case
            if len(analyses_avail) == 0:
                unique_kwargs = kwargs_for_missing

            analyses_avail = get_latest_analyses(user, function_id, topography_ids)\
                  .filter(topography__surface__in=readable_surfaces)

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
            topographies_missing=topographies_missing,  # topographies for which there is no Analysis object yet
            topography_ids_requested_json=json.dumps(topography_ids),  # can be used to retrigger analyses
            extra_warnings=[],  # use list of dicts of form {'alert_class': 'alert-info', 'message': 'your message'}
        ))

        return context

    def get(self, request, *args, **kwargs):
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

        topography_colors = OrderedDict()  # key: Topography instance
        topography_names = []

        series_dashes = OrderedDict()  # key: series name
        series_names = []

        # Also give each series a symbol (only used for small number of points)
        # series_symbols = OrderedDict()  # key: series name

        #
        # Traverse analyses and plot lines
        #
        js_code = ""
        js_args = {}

        special_values = []  # elements: (topography, quantity name, value, unit string)

        for analysis in analyses_success:

            topography_name = analysis.topography.name

            #
            # find out colors for topographies
            #
            if analysis.topography not in topography_colors:
                topography_colors[analysis.topography] = next(color_cycle)
                topography_names.append(analysis.topography.name)

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

                legend_entry = topography_name + ": " + series_name

                curr_color = topography_colors[analysis.topography]
                curr_dash = series_dashes[series_name]
                # curr_symbol = series_symbols[series_name]

                # hover_name = "{} for '{}'".format(series_name, topography_name)

                line_glyph = plot.line('x', 'y', source=source, legend=legend_entry,
                                       line_color=curr_color,
                                       line_dash=curr_dash, name=topography_name)
                if show_symbols:
                    symbol_glyph = plot.scatter('x', 'y', source=source,
                                                legend=legend_entry,
                                                marker='circle',
                                                size=10,
                                                line_color=curr_color,
                                                line_dash=curr_dash,
                                                fill_color=curr_color,
                                                name=topography_name)

                #
                # Prepare JS code to toggle visibility
                #
                series_idx = series_names.index(series_name)
                topography_idx = topography_names.index(topography_name)

                # prepare unique id for this line
                glyph_id = f"glyph_{topography_idx}_{series_idx}_line"
                js_args[glyph_id] = line_glyph  # mapping from Python to JS

                # only indices of visible glyphs appear in "active" lists of both button groups
                js_code += f"{glyph_id}.visible = series_btn_group.active.includes({series_idx}) " \
                           + f"&& topography_btn_group.active.includes({topography_idx});"

                if show_symbols:
                    # prepare unique id for this symbols
                    glyph_id = f"glyph_{topography_idx}_{series_idx}_symbol"
                    js_args[glyph_id] = symbol_glyph  # mapping from Python to JS

                    # only indices of visible glyphs appear in "active" lists of both button groups
                    js_code += f"{glyph_id}.visible = series_btn_group.active.includes({series_idx}) " \
                               + f"&& topography_btn_group.active.includes({topography_idx});"

            #
            # Collect special values to be shown in the result card
            #
            if 'scalars' in analysis.result_obj:
                for scalar_name, scalar_dict in analysis.result_obj['scalars'].items():
                    try:
                        scalar_unit = scalar_dict['unit']
                        if scalar_unit == '1':
                            scalar_unit = ''  # we don't want to display '1' as unit
                        special_values.append((analysis.topography, scalar_name,
                                               scalar_dict['value'], scalar_unit))
                    except (KeyError, IndexError):
                        _log.warning("Cannot display scalar '%s' given as '%s'. Skipping.", scalar_name, scalar_dict)
                        special_values.append((analysis.topography, scalar_name, str(scalar_dict), ''))

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
        topo_names = list(t.name for t in topography_colors.keys())

        series_button_group = CheckboxGroup(
            labels=series_names,
            css_classes=["topobank-series-checkbox"],
            visible=False,
            active=list(range(len(series_names))))  # all active

        topography_button_group = CheckboxGroup(
            labels=topo_names,
            css_classes=["topobank-topography-checkbox"],
            visible=False,
            active=list(range(len(topo_names))))  # all active

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
        # """.format(card_idx)

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
            topography_colors=json.dumps(list(topography_colors.values())),
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
                    topography_name=(analysis.topography.name,)*len(analysis_result['mean_pressures']),
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
                labels.append(analysis.topography.name)

                #
                # find out colors for topographies
                #
                if analysis.topography not in topography_colors:
                    topography_colors[analysis.topography] = next(color_cycle)
                    topography_names.append(analysis.topography.name)

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

        unique_kwargs = context['unique_kwargs']
        if unique_kwargs:
            initial_calc_kwargs = unique_kwargs
        else:
            # default initial arguments for form if we don't have unique common arguments
            contact_mechanics_func = AnalysisFunction.objects.get(pyfunc=contact_mechanics.__name__)
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

        context['limits_calc_kwargs'] = CONTACT_MECHANICS_KWARGS_LIMITS

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

    # args_dict = request_method
    try:
        function_id = int(request_method.get('function_id'))
        topography_ids = [int(tid) for tid in request_method.getlist('topography_ids[]')]
        function_kwargs_json = request_method.get('function_kwargs_json')
    except (KeyError, ValueError, TypeError):
        return JsonResponse({'error': 'error in request data'}, status=400)

    #
    # Interpret given arguments
    #
    function = AnalysisFunction.objects.get(id=function_id)
    topographies = Topography.objects.filter(id__in=topography_ids)
    function_kwargs = json.loads(function_kwargs_json)

    allowed = True
    for topo in topographies:
        allowed &= user.has_perm('view_surface', topo.surface)
        if not allowed:
            break

    if allowed:
        analyses = [request_analysis(user, function, topo, **function_kwargs) for topo in topographies]

        status = 200

        #
        # create a collection of analyses such that points to all analyses
        #
        collection = AnalysisCollection.objects.create(name=f"{function.name} for {len(topographies)} topographies.",
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

    unit = analysis.topography.unit

    if user.has_perm('view_surface', analysis.topography.surface):

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

            topo = analysis.topography
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
            },
            {
                'title': f"{topo.name}",
                'icon': "file-o",
                'href': reverse('manager:topography-detail', kwargs=dict(pk=topo.pk)),
                'active': False,
                'login_required': False,
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
            }
        )
    return tabs


class AnalysisFunctionDetailView(DetailView):
    model = AnalysisFunction
    template_name = "analysis/analyses_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        function = self.object

        topographies, surfaces, tags = selected_instances(self.request)
        effective_topographies = instances_to_topographies(topographies, surfaces, tags)

        # Do we have permission for all of these?
        user = self.request.user
        effective_topographies = [t for t in effective_topographies if user.has_perm('view_surface', t.surface)]

        card = dict(function=function,
                    topography_ids_json=json.dumps([t.id for t in effective_topographies]))

        context['card'] = card

        # Decide whether to open extra tabs for surface/topography details
        tabs = extra_tabs_if_single_item_selected(topographies, surfaces)
        tabs.extend([
            {
                'title': f"Analyze",
                'icon': "area-chart",
                'href': reverse('analysis:list'),
                'active': False,
                'login_required': False,
            },
            {
                'title': f"{function.name}",
                'icon': "area-chart",
                'href': self.request.path,
                'active': True,
                'login_required': False,
            }
        ])
        context['extra_tabs'] = tabs

        return context


class AnalysesListView(FormView):
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
            topographies = set(a.topography for a in collection.analyses.all())

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
        """Returns selected functions as saved in session or, if given, in GET parameters.
        """
        function_ids = request.session.get('selected_functions', [])
        functions = AnalysisFunction.objects.filter(id__in=function_ids)
        return functions

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        selected_functions = self._selected_functions(self.request)
        topographies, surfaces, tags = selected_instances(self.request)
        effective_topographies = instances_to_topographies(topographies, surfaces, tags)

        # Do we have permission for all of these?
        user = self.request.user
        effective_topographies = [t for t in effective_topographies if user.has_perm('view_surface', t.surface)]

        # for displaying result card, we need a dict for each card,
        # which then can be used to load the result data in the background
        cards = []
        for function in selected_functions:
            cards.append(dict(function=function,
                              topography_ids_json=json.dumps([t.id for t in effective_topographies])))

        context['cards'] = cards

        #
        # Decide whether to open extra tabs for surface/topography details
        #

        # Decide whether to open extra tabs for surface/topography details
        tabs = extra_tabs_if_single_item_selected(topographies, surfaces)
        tabs.append(
            {
                'title': f"Analyze",
                'icon': "area-chart",
                'href': self.request.path,
                'active': True,
                'login_required': False,
            }
        )
        context['extra_tabs'] = tabs

        return context


#######################################################################
# Download views
#######################################################################


def download_analyses(request, ids, card_view_flavor, file_format):
    """Returns a file comprised from analyses results.

    :param request:
    :param ids: comma separated string with analyses ids
    :param card_view_flavor: card view flavor, see CARD_VIEW_FLAVORS
    :param file_format: requested file format
    :return:
    """

    #
    # Check permissions and collect analyses
    #
    user = request.user
    if not user.is_authenticated:
        return HttpResponseForbidden()

    analyses_ids = [int(i) for i in ids.split(',')]

    analyses = []

    for aid in analyses_ids:
        analysis = Analysis.objects.get(id=aid)

        #
        # Check whether user has view permission for requested analysis
        #
        if not user.has_perm("view_surface", analysis.topography.surface):
            return HttpResponseForbidden()

        analyses.append(analysis)

    #
    # Check flavor and format argument
    #
    card_view_flavor = card_view_flavor.replace('_', ' ')  # may be given with underscore in URL
    if not card_view_flavor in CARD_VIEW_FLAVORS:
        return HttpResponseBadRequest("Unknown card view flavor '{}'.".format(card_view_flavor))

    download_response_functions = {
        ('plot', 'xlsx'): download_plot_analyses_to_xlsx,
        ('plot', 'txt'): download_plot_analyses_to_txt,
        ('contact mechanics', 'zip'): download_contact_mechanics_analyses_as_zip,
    }

    #
    # Dispatch
    #
    key = (card_view_flavor, file_format)
    if key not in download_response_functions:
        return HttpResponseBadRequest(
            "Cannot provide a download for card view flavor {} in file format ".format(card_view_flavor))

    return download_response_functions[key](request, analyses)


def download_plot_analyses_to_txt(request, analyses):
    # TODO: It would probably be useful to use the (some?) template engine for this.
    # TODO: We need a mechanism for embedding references to papers into output.

    # Pack analysis results into a single text file.
    f = io.StringIO()
    for i, analysis in enumerate(analyses):
        if i == 0:
            f.write('# {}\n'.format(analysis.function) +
                    '# {}\n'.format('=' * len(str(analysis.function))))

            f.write('# IF YOU USE THIS DATA IN A PUBLICATION, PLEASE CITE XXX.\n' +
                    '\n')

        topography = analysis.topography
        topo_creator = topography.creator

        f.write('# Topography: {}\n'.format(topography.name) +
                '# {}\n'.format('=' * (len('Topography: ') + len(str(topography.name)))) +
                '# Creator: {}\n'.format(topo_creator) +
                '# Further arguments of analysis function: {}\n'.format(analysis.get_kwargs_display()) +
                '# Start time of analysis task: {}\n'.format(analysis.start_time) +
                '# End time of analysis task: {}\n'.format(analysis.end_time) +
                '# Duration of analysis task: {}\n'.format(analysis.duration()))
        if analysis.configuration is None:
            f.write('# Versions of dependencies (like "SurfaceTopography") are unknown for this analysis.\n')
            f.write('# Please recalculate in order to have version information here.')
        else:
            versions_used = analysis.configuration.versions.order_by('dependency__import_name')

            for version in versions_used:
                f.write(f"# Version of '{version.dependency.import_name}': {version.number_as_string()}\n")
        f.write('\n')

        result = pickle.loads(analysis.result)
        xunit_str = '' if result['xunit'] is None else ' ({})'.format(result['xunit'])
        yunit_str = '' if result['yunit'] is None else ' ({})'.format(result['yunit'])
        header = 'Columns: {}{}, {}{}'.format(result['xlabel'], xunit_str, result['ylabel'], yunit_str)

        for series in result['series']:
            np.savetxt(f, np.transpose([series['x'], series['y']]),
                       header='{}\n{}\n{}'.format(series['name'], '-' * len(series['name']), header))
            f.write('\n')

    # Prepare response object.
    response = HttpResponse(f.getvalue(), content_type='application/text')
    response['Content-Disposition'] = 'attachment; filename="{}"'.format('{}.txt'.format(analysis.function.pyfunc))

    # Close file and return response.
    f.close()
    return response


def download_plot_analyses_to_xlsx(request, analyses):
    # TODO: We need a mechanism for embedding references to papers into output.

    # Pack analysis results into a single text file.
    f = io.BytesIO()
    excel = pd.ExcelWriter(f)

    # Analyze topography names and store a distinct name
    # which can be used in sheet names if topography names are not unique
    topography_names_in_sheet_names = [a.topography.name for a in analyses]

    for tn in set(topography_names_in_sheet_names):  # iterate over distinct names

        # replace name with a unique one using a counter
        indices = [i for i, a in enumerate(analyses) if a.topography.name == tn]

        if len(indices) > 1:  # only rename if not unique
            for k, idx in enumerate(indices):
                topography_names_in_sheet_names[idx] += f" ({k + 1})"

    # Global properties and values.
    properties = []
    values = []

    for i, analysis in enumerate(analyses):

        if i == 0:
            properties = ["Function"]
            values = [str(analysis.function)]

        properties += ['Topography', 'Creator',
                       'Further arguments of analysis function', 'Start time of analysis task',
                       'End time of analysis task', 'Duration of analysis task']
        values += [str(analysis.topography.name), str(analysis.topography.creator),
                   analysis.get_kwargs_display(), str(analysis.start_time),
                   str(analysis.end_time), str(analysis.duration())]
        if analysis.configuration is None:
            properties.append("Versions of dependencies")
            values.append("Unknown. Please recalculate this analysis in order to have version information here.")
        else:
            versions_used = analysis.configuration.versions.order_by('dependency__import_name')

            for version in versions_used:
                properties.append(f"Version of '{version.dependency.import_name}'")
                values.append(f"{version.number_as_string()}")
        # We want an empty line on the properties sheet in order to distinguish the topographies
        properties.append("")
        values.append("")

        result = pickle.loads(analysis.result)
        column1 = '{} ({})'.format(result['xlabel'], result['xunit'])
        column2 = '{} ({})'.format(result['ylabel'], result['yunit'])

        # determine name of topography in sheet name

        for series in result['series']:
            df = pd.DataFrame({column1: series['x'], column2: series['y']})

            sheet_name = '{} - {}'.format(topography_names_in_sheet_names[i],
                                          series['name']).replace('/', ' div ')
            df.to_excel(excel, sheet_name=mangle_sheet_name(sheet_name))
    df = pd.DataFrame({'Property': properties, 'Value': values})
    df.to_excel(excel, sheet_name='INFORMATION', index=False)
    excel.close()

    # Prepare response object.
    response = HttpResponse(f.getvalue(),
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="{}"'.format('{}.xlsx'.format(analysis.function.pyfunc))

    # Close file and return response.
    f.close()
    return response


def download_contact_mechanics_analyses_as_zip(request, analyses):
    """Provides a ZIP file with contact mechanics data.

    :param request: HTTPRequest
    :param analyses: sequence of Analysis instances
    :return: HTTP Response with file download
    """

    bytes = BytesIO()

    zf = zipfile.ZipFile(bytes, mode='w')

    #
    # Add directories and files for all analyses
    #
    zip_dirs = set()

    for analysis in analyses:

        zip_dir = analysis.topography.name
        if zip_dir in zip_dirs:
            # make directory unique
            zip_dir += "-{}".format(analysis.topography.id)
        zip_dirs.add(zip_dir)

        #
        # Add a csv file with plot data
        #
        analysis_result = analysis.result_obj

        col_keys = ['mean_pressures', 'total_contact_areas', 'mean_gaps', 'converged', 'data_paths']
        col_names = ["Normalized pressure p/E*", "Fractional contact area A/A0", "Normalized mean gap u/h_rms",
                     "converged", "filename"]

        col_dicts = {col_names[i]:analysis_result[k] for i,k in enumerate(col_keys)}
        plot_df = pd.DataFrame(col_dicts)
        plot_df['filename'] = plot_df['filename'].map(lambda fn: os.path.split(fn)[1])  # only simple filename

        plot_filename_in_zip = os.path.join(zip_dir, 'plot.csv')
        zf.writestr(plot_filename_in_zip, plot_df.to_csv())

        #
        # Add all files from storage
        #
        prefix = analysis.storage_prefix

        directories, filenames = default_storage.listdir(prefix)

        for file_no, fname in enumerate(filenames):

            input_file = default_storage.open(prefix + fname)

            filename_in_zip = os.path.join(zip_dir, fname)

            try:
                zf.writestr(filename_in_zip, input_file.read())
            except Exception as exc:
                zf.writestr("errors-{}.txt".format(file_no),
                            "Cannot save file {} in ZIP, reason: {}".format(filename_in_zip, str(exc)))

    #
    # Add a Readme file
    #
    zf.writestr("README.txt",\
                f"""
Contents of this ZIP archive
============================
This archive contains data from contact mechanics calculation.

Each directory corresponds to one topography and is named after the topography.
Inside you find two types of files:

- a simple CSV file ('plot.csv')
- a couple of classical netCDF files (Extension '.nc')

The file 'plot.csv' contains a table with the data used in the plot,
one line for each calculation step. It has the following columns:

- Zero-based index column
- Normalized pressure in units of p/E*
- Fractional contact area in units of A/A0
- Normalized mean gap in units of u/h_rms
- A boolean flag (True/False) which indicates whether the calculation converged
  within the given limit
- Filename of the NetCDF file (order of filenames may be different than index)

So each line also refers to one NetCDF file in the directory, it corresponds to
one external pressure. Inside the NetCDF file you'll find the variables

* `contact_points`: boolean array, true if point is in contact
* `pressure`: floating-point array containing local pressure (in units of `E*`)
* `gap`: floating-point array containing the local gap
* `displacement`: floating-point array containing the local displacements

as well as the attributes

* `mean_pressure`: mean pressure (in units of `E*`)
* `total_contact_area`: total contact area (fractional)

In order to read the data, you can use a netCDF library.
Here are some examples:

Accessing the NetCDF files
==========================

### Python

Given the package [`netcdf4-python`](http://netcdf4-python.googlecode.com/) is installed:

```
import netCDF4
ds = netCDF4.Dataset("result-step-0.nc")
print(ds)
pressure = ds['pressure'][:]
mean_pressure = ds.mean_pressure
```

Another convenient package you can use is [`xarray`](xarray.pydata.org/).

### Matlab

In order to read the pressure map in Matlab, use

```
ncid = netcdf.open("result-step-0.nc",'NC_NOWRITE');
varid = netcdf.inqVarID(ncid,"pressure");
pressure = netcdf.getVar(ncid,varid);
```

Have look in the official Matlab documentation for more information.

Version information
===================

SurfaceTopography: {SurfaceTopography.__version__}
ContactMechanics:  {ContactMechanics.__version__}
muFFT:             {muFFT.version.description()}
NuMPI:             {NuMPI.__version__}
TopoBank:          {settings.TOPOBANK_VERSION}
    """)

    zf.close()

    # Prepare response object.
    response = HttpResponse(bytes.getvalue(),
                            content_type='application/x-zip-compressed')
    response['Content-Disposition'] = 'attachment; filename="{}"'.format('contact_mechanics.zip')

    return response

"""

"""
from bokeh.layouts import row, column, widgetbox, layout
from bokeh.models import ColumnDataSource, CustomJS, AjaxDataSource
from bokeh.models.widgets import CheckboxButtonGroup, CheckboxGroup, Panel, Tabs, TableColumn, DataTable, Button
from bokeh.models.widgets.markups import Paragraph, Div
from bokeh.models.formatters import FuncTickFormatter
from bokeh.models.ranges import DataRange1d
from bokeh.plotting import figure
from bokeh.palettes import Category10
from bokeh.embed import components
import itertools
import json
from collections import OrderedDict
from pint import UnitRegistry, UndefinedUnitError

import logging
_log = logging.getLogger(__name__)

def function_card_context(analyses):
    """Context for card template for analysis results.

    :param card_idx: integer number identifying the card on a page
    :param analyses: iterable of Analysis instances, tasks must be ready + successful
    :return: context
    TODO explain context
    """

    if len(analyses)==0:
        return dict(plot_script="",
                    plot_div="No analysis available",
                    special_values=[],
                    topography_colors=json.dumps(list()),
                    series_dashes=json.dumps(list()))


    #
    # Prepare plot, controls, and table with special values..
    #

    first_analysis_result = analyses[0].result_obj
    title = first_analysis_result['name']

    xunit = first_analysis_result['xunit']
    yunit = first_analysis_result['yunit']

    ureg = UnitRegistry() # for unit conversion for each analysis individually, see below

    #
    # set xrange, yrange -> automatic bounds for zooming
    #
    x_range = DataRange1d(bounds='auto')  # if min+max not given, calculate from data of render
    y_range = DataRange1d(bounds='auto')

    def get_axis_type(key):
        return first_analysis_result.get(key) or "linear"

    x_axis_label = first_analysis_result['xlabel'] + f' ({xunit})'
    y_axis_label = first_analysis_result['ylabel'] + f' ({yunit})'

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
                  tools="crosshair,pan,reset,save,wheel_zoom,box_zoom")

    #
    # Prepare helpers for dashes and colors
    #
    color_cycle = itertools.cycle(Category10[10])
    dash_cycle = itertools.cycle(['solid', 'dashed', 'dotted', 'dotdash', 'dashdot'])

    series_dashes = OrderedDict() # key: series name
    series_names = []
    topography_colors = OrderedDict() # key: Topography instance
    topography_names = []

    #
    # Traverse analyses and plot lines
    #
    js_code = ""
    js_args = {}

    special_values = [] # elements: (topography, quantity name, value, unit string)

    for analysis in analyses:

        topography_name = analysis.topography.name

        #
        # find out colors for topographies
        #
        if analysis.topography not in topography_colors:
            topography_colors[analysis.topography] = next(color_cycle)
            topography_names.append(analysis.topography.name)

        if analysis.task_state == analysis.FAILURE:
            continue # should not happen if only called with successful analyses
        elif analysis.task_state == analysis.SUCCESS:
            series = analysis.result_obj['series']
        else:
            # not ready yet
            continue # should not happen if only called with successful analyses

        #
        # find out scale for data
        #
        analysis_result = analysis.result_obj

        try:
            analysis_xscale = ureg.convert(1, xunit, analysis_result['xunit'])
            analysis_yscale = ureg.convert(1, yunit, analysis_result['yunit'])
        except UndefinedUnitError as exc:
            _log.error("Cannot convert units when displaying results for analysis with id %s. Cause: %s",
                       analysis.id, str(exc))
            continue
            # TODO How to handle such an error here?

        for s in series:
            # One could use AjaxDataSource for retrieving the results, but useful if we are already in AJAX call?
            source = ColumnDataSource(data=dict(x=analysis_xscale*s['x'],
                                                y=analysis_yscale*s['y']))

            series_name = s['name']
            #
            # find out dashes for data series
            #
            if series_name not in series_dashes:
                series_dashes[series_name] = next(dash_cycle)
                series_names.append(series_name)

            #
            # Actually plot the line
            #
            legend_entry = topography_name+": "+series_name

            glyph = plot.line('x', 'y', source=source, legend=legend_entry,
                              line_color=topography_colors[analysis.topography],
                              line_dash=series_dashes[series_name])

            #
            # Prepare JS code to toggle visibility
            #
            series_idx = series_names.index(series_name)
            topography_idx = topography_names.index(topography_name)

            # prepare unique id for this line
            glyph_id = f"glyph_{topography_idx}_{series_idx}"
            js_args[glyph_id]= glyph # mapping from Python to JS

            # only indices of visible glyphs appear in "active" lists of both button groups
            js_code += f"{glyph_id}.visible = series_btn_group.active.includes({series_idx}) "\
                       +f"&& topography_btn_group.active.includes({topography_idx});"

        #
        # Collect special values to be shown in the result card
        #
        if 'scalars' in analysis.result_obj:
            for k,v in analysis.result_obj['scalars'].items():
                special_values.append((analysis.topography, k, v, analysis.topography.height_unit))

    #
    # Final configuration of the plot
    #

    # plot.legend.click_policy = "hide" # can be used to disable lines by clicking on legend
    plot.legend.visible = False # we have extra widgets to disable lines
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
                    active=list(range(len(series_names)))) # all active

    topography_button_group = CheckboxGroup(
                    labels=topo_names,
                    css_classes=["topobank-topography-checkbox"],
                    active=list(range(len(topo_names)))) # all active

    # extend mapping of Python to JS objects
    js_args['series_btn_group'] = series_button_group
    js_args['topography_btn_group'] = topography_button_group

    # add code for setting styles of widgetbox elements
    #js_code += """
    #style_checkbox_labels({});
    #""".format(card_idx)

    toggle_lines_callback = CustomJS(args=js_args, code=js_code)

    #
    # TODO Idea: Generate DIVs with Markup of colors and dashes and align with Buttons/Checkboxes
    #
    widgets = row(widgetbox(Paragraph(text="Topographies"), topography_button_group),
                  widgetbox(Paragraph(text="Data Series"), series_button_group))

    series_button_group.js_on_click(toggle_lines_callback)
    topography_button_group.js_on_click(toggle_lines_callback)

    #
    # Convert plot and widgets to HTML, add meta data for template
    #
    script, div = components(column(plot, widgets, sizing_mode='scale_width'))

    context = dict(plot_script=script,
                   plot_div=div,
                   special_values=special_values,
                   topography_colors=json.dumps(list(topography_colors.values())),
                   series_dashes=json.dumps(list(series_dashes.values())))

    return context

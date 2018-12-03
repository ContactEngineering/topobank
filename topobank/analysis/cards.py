"""

"""
from bokeh.layouts import row, column, widgetbox, layout
from bokeh.models import ColumnDataSource, CustomJS, AjaxDataSource
from bokeh.models.widgets import CheckboxButtonGroup, CheckboxGroup, Panel, Tabs, TableColumn, DataTable, Button
from bokeh.models.widgets.markups import Paragraph, Div
from bokeh.models.formatters import FuncTickFormatter
from bokeh.plotting import figure
from bokeh.palettes import Category10
from bokeh.embed import components
import itertools
import json
from collections import OrderedDict
from celery.states import READY_STATES
from ..manager.utils import optimal_unit
import time

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

    # TODO find out common units, convert data
    xunit = first_analysis_result['xunit']
    yunit = first_analysis_result['yunit']

    # TODO: set xrange, yrange, bounds for zooming

    def get_axis_type(key):
        return first_analysis_result.get(key) or "linear"

    plot = figure(title=title,
                  # plot_width=700,
                  sizing_mode='stretch_both', # TODO how does automatic resizing work?
                  x_axis_label=f'x ({xunit})',
                  y_axis_label=f'y ({yunit})',
                  x_axis_type=get_axis_type('xscale'),
                  y_axis_type=get_axis_type('yscale'),
                  tools="crosshair,pan,reset,save,wheel_zoom,box_zoom")

    color_cycle = itertools.cycle(Category10[10])
    dash_cycle = itertools.cycle(['solid', 'dashed', 'dotted', 'dotdash', 'dashdot'])

    series_dashes = OrderedDict() # key: series name
    series_names = []
    topography_colors = OrderedDict() # key: Topography instance
    topography_names = []

    js_code = ""
    js_args = {}

    special_values = [] # elements: (topography, quantity name, value, unit string)

    for analysis in analyses:

        topography_name = analysis.topography.name

        #
        # find out colors
        #
        if analysis.topography not in topography_colors:
            topography_colors[analysis.topography] = next(color_cycle)
            topography_names.append(analysis.topography.name)

        if analysis.task_state == analysis.FAILURE:
            # TODO handle failure
            continue
        elif analysis.task_state == analysis.SUCCESS:
            series = analysis.result_obj['series']
        else:
            # not ready yet
            continue # TODO add/leave spinner

        for s in series:
            # TODO use AjaxDataSource for retrieving the results??
            source = ColumnDataSource(data=dict(x=s['x'], y=s['y']))

            series_name = s['name']
            #
            # find out dashes
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

        if 'scalars' in analysis.result_obj:
            for k,v in analysis.result_obj['scalars'].items():
                special_values.append((analysis.topography, k, v, analysis.topography.height_unit))

    # plot.legend.click_policy = "hide"
    plot.legend.visible = False
    plot.toolbar.logo = None
    plot.xaxis.axis_label_text_font_style = "normal"
    plot.yaxis.axis_label_text_font_style = "normal"
    plot.xaxis.major_label_text_font_size = "12pt"
    plot.yaxis.major_label_text_font_size = "12pt"

    # see js function "format_exponential()" in project.js file
    plot.xaxis.formatter = FuncTickFormatter(code="return format_exponential(tick);")
    plot.yaxis.formatter = FuncTickFormatter(code="return format_exponential(tick);")

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

    script, div = components(column(plot, widgets))

    context = dict(plot_script=script,
                   plot_div=div,
                   special_values=special_values,
                   topography_colors=json.dumps(list(topography_colors.values())),
                   series_dashes=json.dumps(list(series_dashes.values())))

    return context

"""

"""
import numpy as np

from bokeh.layouts import row, column, widgetbox, layout
from bokeh.models import ColumnDataSource, CustomJS, AjaxDataSource
from bokeh.models.widgets import CheckboxButtonGroup, CheckboxGroup
from bokeh.models.widgets.markups import Paragraph
from bokeh.plotting import figure
from bokeh.palettes import Category10
import itertools

def make_result_model(analyses):
    """Create document for usage ith bokeh server

    :return: bokeh model
    """

    if len(analyses) == 0:
        return row() # empty bokeh plot row row

    first_analysis_result = analyses[0].result_obj
    title = first_analysis_result['name']

    # TODO find out common units, convert data
    xunit = first_analysis_result['xunit']
    yunit = first_analysis_result['yunit']

    plot = figure(title=title,
                  x_axis_label=f'x ({xunit})',
                  y_axis_label=f'y ({yunit})',
                  tools="crosshair,pan,reset,save,wheel_zoom,box_zoom")

    # TODO: set xrange, yrange, bounds?
    # TODO axis scaling, which one wins?
    # TODO figure out axis scale

    color_cycle = itertools.cycle(Category10[10])
    dash_cycle = itertools.cycle(['solid', 'dashed', 'dotted', 'dotdash', 'dashdot'])

    series_dashes = {}
    series_names = []
    topography_colors = {}
    topography_names = []

    js_code = ""
    js_args = {}

    for analysis in analyses:

        if analysis.task_state == analysis.FAILURE:
            # TODO handle failure
            continue
        elif analysis.task_state == analysis.SUCCESS:
            series = analysis.result_obj['series']
        else:
            # not ready yet
            continue # TODO add/leave spinner

        for s in series:
            # TODO use AjaxDataSource for retrieving the results
            source = ColumnDataSource(data=dict(x=s['x'], y=s['y']))

            series_name = s['name']
            topography_name = analysis.topography.name

            #
            # find out colors and dashes
            #
            if analysis.topography not in topography_colors:
                topography_colors[analysis.topography] = next(color_cycle)
                topography_names.append(analysis.topography.name)

            if series_name not in series_dashes:
                series_dashes[series_name] = next(dash_cycle)
                series_names.append(series_name)

            #
            # Actually plot
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

            glyph_id = f"glyph_{topography_idx}_{series_idx}"
            js_args[glyph_id]= glyph # mapping from Python to JS

            # only visible of this glyphs appears in active lists of both button groups
            js_code += f"{glyph_id}.visible = series_btn_group.active.includes({series_idx}) "\
                       +f"&& topography_btn_group.active.includes({topography_idx});"

    # create a AjaxDataSource for every series
    # for series in
    plot.legend.click_policy = "hide"
    plot.xaxis.axis_label_text_font_style = "normal"
    plot.yaxis.axis_label_text_font_style = "normal"

    topo_names = list(t.name for t in topography_colors.keys())

    series_button_group = CheckboxGroup(
                    labels=series_names,
                    active=list(range(len(series_names)))) # all active
    # series_button_group.js_on_click(CustomJS(arg))

    topography_button_group = CheckboxGroup(
                    labels=topo_names,
                    active=list(range(len(topo_names)))) # all active

    # extend mapping of Python to JS objects
    js_args['series_btn_group'] = series_button_group
    js_args['topography_btn_group'] = topography_button_group

    callback = CustomJS(args=js_args, code=js_code)

    widgets = row(widgetbox(Paragraph(text="Topographies"), topography_button_group),
                  widgetbox(Paragraph(text="Data Series"), series_button_group))

    series_button_group.js_on_click(callback)
    topography_button_group.js_on_click(callback)

    return column(plot, widgets, width=600)



/* Project specific Javascript goes here. */

/*
Formatting hack to get around crispy-forms unfortunate hardcoding
in helpers.FormHelper:

    if template_pack == 'bootstrap4':
        grid_colum_matcher = re.compile('\w*col-(xs|sm|md|lg|xl)-\d+\w*')
        using_grid_layout = (grid_colum_matcher.match(self.label_class) or
                             grid_colum_matcher.match(self.field_class))
        if using_grid_layout:
            items['using_grid_layout'] = True

Issues with the above approach:

1. Fragile: Assumes Bootstrap 4's API doesn't change (it does)
2. Unforgiving: Doesn't allow for any variation in template design
3. Really Unforgiving: No way to override this behavior
4. Undocumented: No mention in the documentation, or it's too hard for me to find
*/
$('.form-group').removeClass('row');

function render_scatter_plot(element, json_data) {
    var xScale = new Plottable.Scales.Linear();
    var yScale = new Plottable.Scales.Linear();

    var xAxis = new Plottable.Axes.Numeric(xScale, "bottom");
    var yAxis = new Plottable.Axes.Numeric(yScale, "left");

    var xAxisLabel = new Plottable.Components.AxisLabel("Height")
        .yAlignment("center");
    var yAxisLabel = new Plottable.Components.AxisLabel("Probability")
        .xAlignment("center")
        .angle(-90);

    var data = json_data.result.hist.map(function (value, index) {
        return {x: (this[index] + this[index + 1]) / 2, y: value};
    }, json_data.result.bin_edges);

    var dataset = new Plottable.Dataset(data);

    var plot = new Plottable.Plots.Line()
        .x(function (d) { return d.x; }, xScale)
        .y(function (d) { return d.y; }, yScale)
        .addDataset(dataset);

    var chart = new Plottable.Components.Table([
        [yAxisLabel, yAxis, plot],
        [null, null, xAxis],
        [null, null, xAxisLabel]
    ]);

    chart.renderTo(element);
    $(element).width('100%');
    $(element).height('300px');
    chart.redraw();

    $(element).data('chart', chart);
}

/*
 * Updated scatter plot for a certain task. Continually poll task results if data not yet available.
 */
function scatter_plot(element) {
    $.get($(element).data('src'), function (data) {
        if (data.task_state == 'pe' || data.task_state == 'st') {
            setTimeout(function () {
                scatter_plot(element);
            }, 1000);
        }
        else {
            render_scatter_plot(element, data);
        }
    });
}

$(document).ready(function($) {
    $('.clickable-table-row').click(function () {
        window.document.location = $(this).data("href");
    });

    $('.topobank-scatter-plot').each(function () {
        scatter_plot(this);
    });

    /* Resize all plots when window is resized. */
    $(window).on('resize', function() {
       $('.topobank-plot-resize').each(function () {
          $(this).data('chart').redraw();
       });
    });
});

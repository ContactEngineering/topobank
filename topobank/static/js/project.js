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

function render_plot(element, descr) {
    var xScale = new Plottable.Scales.Linear();
    var yScale = new Plottable.Scales.Linear();

    var xAxis = new Plottable.Axes.Numeric(xScale, "bottom");
    var yAxis = new Plottable.Axes.Numeric(yScale, "left");

    var xAxisLabel = new Plottable.Components.Label(descr.xlabel)
        .yAlignment("center");
    var yAxisLabel = new Plottable.Components.Label(descr.ylabel)
        .xAlignment("center")
        .angle(-90);

    var plots = [];
    descr.series.forEach(function (item) {
        var dataset = new Plottable.Dataset(
            item.y.map(function (value, index) {
                return {x: (this[index] + this[index + 1]) / 2, y: value};
            }, item.x));

        var plot = new Plottable.Plots.Line()
            .x(function (d) {
                return d.x;
            }, xScale)
            .y(function (d) {
                return d.y;
            }, yScale)
            .addDataset(dataset);

        plots.push(plot);
    });

    var chart = new Plottable.Components.Table([
        [yAxisLabel, yAxis, new Plottable.Components.Group(plots)],
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
function plot(element) {
    $.get($(element).data('src'), function (data) {
        if (data.task_state == 'pe' || data.task_state == 'st') {
            setTimeout(function () {
                plot(element);
            }, 1000);
        }
        else {
            render_plot(element, data.result);
        }
    });
}

$(document).ready(function($) {
    $('.clickable-table-row').click(function () {
        window.document.location = $(this).data("href");
    });

    /* Initiate all plots, or rather first AJAX request to get plot data. */
    $('.topobank-scatter-plot').each(function () {
        plot(this);
    });

    /* Resize all plots when window is resized. */
    $(window).on('resize', function() {
       $('.topobank-plot-resize').each(function () {
          $(this).data('chart').redraw();
       });
    });
});

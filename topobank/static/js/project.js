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
    var color_abbreviations = {
        'k': 'black',
        'r': 'red',
    };
    var symbol_factories = {
        'o': Plottable.SymbolFactories.circle(),
        '+': Plottable.SymbolFactories.cross(),
        'd': Plottable.SymbolFactories.diamond(),
        's': Plottable.SymbolFactories.square(),
        '^': Plottable.SymbolFactories.triangle(),
        'y': Plottable.SymbolFactories.wye(),
    };

    var xScale, yScale;
    if (descr.xscale == 'log') {
        xScale = new Plottable.Scales.Log();
    }
    else {
        xScale = new Plottable.Scales.Linear();
    }
    if (descr.yscale == 'log') {
        yScale = new Plottable.Scales.Log();
    }
    else {
        yScale = new Plottable.Scales.Linear();
    }

    var xAxis = new Plottable.Axes.Numeric(xScale, "bottom");
    var yAxis = new Plottable.Axes.Numeric(yScale, "left");

    var xlabel = descr.xlabel;
    var ylabel = descr.ylabel;

    if (descr.xunit)  xlabel += ' ('+descr.xunit+')';
    if (descr.yunit)  ylabel += ' ('+descr.yunit+')';

    var xAxisLabel = new Plottable.Components.Label(xlabel)
        .yAlignment("center");
    var yAxisLabel = new Plottable.Components.Label(ylabel)
        .xAlignment("center")
        .angle(-90);

    var names = [];
    descr.series.forEach(function (item) {
       names.push(item.name);
    });

    var color_scale = new Plottable.Scales.Color();
    color_scale.domain(names);

    var plots = [];
    var symbols = [];
    descr.series.forEach(function (item) {
        var style = typeof item.style == 'undefined' ? 'k-' : item.style;

        var dataset = new Plottable.Dataset(
            item.y.map(function (value, index) {
                return {x: (this[index] + this[index + 1]) / 2, y: value};
            }, item.x));

        var line = false;
        var color = undefined;
        var symbol = undefined;
        for (var c of style) {
            if (c == '-') {
                line = true;
            }
            else if (c in color_abbreviations) {
                color = color_abbreviations[c];
            }
            else if (c in symbol_factories) {
                symbol = symbol_factories[c];
            }
            else {
                throw TypeError('Cannot interpret style string: ' + style);
            }
        }

        if (line) {
            var plot = new Plottable.Plots.Line()
                .x(function (d) {
                    return d.x;
                }, xScale)
                .y(function (d) {
                    return d.y;
                }, yScale)
                .addDataset(dataset);
            if (color) {
                plot.attr('stroke', color);
            }
            else {
                plot.attr('stroke', item.name, color_scale);
            }
            plots.push(plot);
        }
        if (symbol) {
            var plot = new Plottable.Plots.Scatter()
                .x(function (d) {
                    return d.x;
                }, xScale)
                .y(function (d) {
                    return d.y;
                }, yScale)
                .symbol(function () {
                    return symbol;
                })
                .addDataset(dataset);
            if (color) {
                plot.attr('stroke', color).attr('fill', color);
            }
            else {
                plot.attr('stroke', item.name, color_scale).attr('fill', item.name, color_scale);
            }
            plots.push(plot);
        }

        symbols.push(symbol);
    });

    var legend = new Plottable.Components.Legend(color_scale);
    legend.symbol(function (datum, index) { s = symbols[index]; return s ? s : Plottable.SymbolFactories.circle(); });

    var chart = new Plottable.Components.Table([
        [null,       null,  legend],
        [yAxisLabel, yAxis, new Plottable.Components.Group(plots)],
        [null,       null,  xAxis, null],
        [null,       null,  xAxisLabel, null]
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
            if ('error' in data.result) {
                $(element).html('Server reported error: ' + data.result.error);
            }
            else {
                render_plot(element, data.result);
                $('.spinner', $(element).parent()).hide();
            }
        }
    }).fail(function () {
        $(element).html('Failed obtaining resource from server: ' + $(element).data('src'));
        $('.spinner', $(element).parent()).hide();
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

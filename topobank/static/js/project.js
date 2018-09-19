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


/* Split a unit string into the base unit and an exponent. E.g.
 *   µm³ => µm, 3
 */
function split_unit(unit_str) {
    if (!unit_str) {
        return {
            unit: undefined,
            exponent: 1,
        }
    }

    var superscript_dict = {
        '⁰': '0',
        '¹': '1',
        '²': '2',
        '³': '3',
        '⁴': '4',
        '⁵': '5',
        '⁶': '6',
        '⁷': '7',
        '⁸': '8',
        '⁹': '9',
        '⁺': '+',
        '⁻': '-',
        '⋅': '.',
    };

    var unit = '';
    var exponent = '';

    for (var c of unit_str) {
        if (c in superscript_dict) {
            exponent += superscript_dict[c];
        }
        else {
            unit += c;
        }
    }
    return {
        unit: unit,
        exponent: exponent.length ? parseInt(exponent) : 1
    };
}

/*
 * Convert numerals inside a string into the unicode superscript equivalent, e.g.
 *   µm3 => µm³
 */
function unicode_superscript(s) {
    superscript_dict = {
        '0': '⁰',
        '1': '¹',
        '2': '²',
        '3': '³',
        '4': '⁴',
        '5': '⁵',
        '6': '⁶',
        '7': '⁷',
        '8': '⁸',
        '9': '⁹',
        '+': '⁺',
        '-': '⁻',
        '.': '⋅',
    };
    return s.split('').map(c => c in superscript_dict ? superscript_dict[c] : c).join('');
}


/*
 * Convert a base unit and an exponent into a unicode string, e.g.
 *   µm, 3 => µm³
 */
function unicode_unit(unit, exponent) {
    if (exponent == 1) {
        return unit;
    }
    else {
        return unicode_superscript(unit + exponent);
    }
}


/*
 * Render data to SVG. This function can be called multiple times for the same element, if multiple data sources are
 * listed for the respective element. The resulting data will then be presented in a single plot. Function handles
 * unit conversion between data sources.
 */
function render_plot(element, descr, unit = undefined) {
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

    /* Figure out units. */
    xunit = split_unit(descr.xunit);
    yunit = split_unit(descr.yunit);

    if (xunit.unit != yunit.unit) {
        throw TypeError('X- and y-axis have different (base) units. Cannot at present handle this.');
    }

    /* If no unit was passed to this function, we default to the unit reported by the server. */
    if (!unit) unit = xunit.unit;

    /* If we have a unit, determine the scale factor between chosen unit and the unit reported by the server. */
    var scale_factor = 1, scale_factor_x = 1, scale_factor_y = 1;
    if (unit) {
        scale_factor = convert(1).from(xunit.unit).to(unit);
        scale_factor_x = scale_factor**xunit.exponent;
        scale_factor_y = scale_factor**yunit.exponent;
    }

    /* Create (linear, log) scales. */
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

    /* Create axes. */
    var xAxis = new Plottable.Axes.Numeric(xScale, "bottom");
    var yAxis = new Plottable.Axes.Numeric(yScale, "left");

    var xlabel = descr.xlabel;
    var ylabel = descr.ylabel;

    if (xunit.unit) xlabel += ' (' + unicode_unit(unit, xunit.exponent) + ')';
    if (yunit.unit) ylabel += ' (' + unicode_unit(unit, yunit.exponent) + ')';

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
                return {x: scale_factor_x*this[index], y: scale_factor_y*value};
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
    legend.symbol(function (datum, index) {
        s = symbols[index];
        return s ? s : Plottable.SymbolFactories.circle();
    });

    var chart = new Plottable.Components.Table([
        [null, null, legend],
        [yAxisLabel, yAxis, new Plottable.Components.Group(plots)],
        [null, null, xAxis, null],
        [null, null, xAxisLabel, null]
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
function plot(element, unit = undefined) {
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
                render_plot(element, data.result, unit);
                $('.spinner', $(element).parent()).hide();
            }
        }
    }).fail(function () {
        $(element).html('Failed obtaining resource from server: ' + $(element).data('src'));
        $('.spinner', $(element).parent()).hide();
    });
}


/*
 * Setup document handlers.
 */
$(document).ready(function ($) {
    $('.clickable-table-row').click(function () {
        window.document.location = $(this).data("href");
    });

    /* Initiate all plots, or rather first AJAX request to get plot data. */
    $('.topobank-scatter-plot').each(function () {
        plot(this);
    });

    /* Resize all plots when window is resized. */
    $(window).on('resize', function () {
        $('.topobank-plot-resize').each(function () {
            $(this).data('chart').redraw();
        });
    });
});

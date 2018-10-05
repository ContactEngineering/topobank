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
function render_plot(element, name_array, plot_descr_array, unit) {
    /* Static dictionaries. */
    var color_abbreviations = {
        'k': 'black',
        'r': 'red',
        'g': 'green',
        'b': 'blue'
    };
    var symbol_abbreviations = {
        'o': Plottable.SymbolFactories.circle(),
        '+': Plottable.SymbolFactories.cross(),
        'd': Plottable.SymbolFactories.diamond(),
        's': Plottable.SymbolFactories.square(),
        '^': Plottable.SymbolFactories.triangle(),
        'y': Plottable.SymbolFactories.wye(),
    };

    /* Check if chart already exists. */
    chart = $(element).data('chart');
    if (chart) chart.destroy();

    /* Scales. */
    var x_scale, y_scale, x_axis, y_axis, x_axis_label, y_axis_label, color_scale;

    /* Individual plots and symbols beloging to those. */
    var plots = {}, symbols = {};

    var names = [];
    for (var i in plot_descr_array) {
        plot_name = name_array[i];
        plot_descr = plot_descr_array[i];
        plot_descr.series.forEach(function (item) {
            if (plot_descr.series.length > 1) {
                names.push(plot_name + ': ' + item.name);
            }
            else {
                names.push(plot_name);
            }
        });
    }

    /* Automatic color selection. */
    color_scale = new Plottable.Scales.Color();
    color_scale.domain(names);

    /* Loop over all plot descriptor dictionaries passed here. */
    for (var i in plot_descr_array) {
        plot_name = name_array[i];
        plot_descr = plot_descr_array[i];

        /* Figure out units. */
        xunit = split_unit(plot_descr.xunit);
        yunit = split_unit(plot_descr.yunit);

        if (xunit.unit != yunit.unit) {
            throw TypeError('X- and y-axis have different (base) units. Cannot at present handle this.');
        }

        /* If no unit was passed to this function, we default to the unit of the first dataset reported by the
           server. */
        if (!unit) unit = xunit.unit;

        /* Now we have a unit, determine the scale factor between chosen unit and the unit reported by the server for
           the present dataset. */
        var scale_factor = 1, scale_factor_x = 1, scale_factor_y = 1;
        if (unit) {
            scale_factor = convert(1).from(xunit.unit).to(unit);
            scale_factor_x = scale_factor ** xunit.exponent;
            scale_factor_y = scale_factor ** yunit.exponent;
        }

        /* Create (linear, log) scales. */
        if (!x_scale) {
            if (plot_descr.xscale == 'log') {
                x_scale = new Plottable.Scales.Log();
            }
            else {
                x_scale = new Plottable.Scales.Linear();
            }
        }
        if (!y_scale) {
            if (plot_descr.yscale == 'log') {
                y_scale = new Plottable.Scales.Log();
            }
            else {
                y_scale = new Plottable.Scales.Linear();
            }
        }

        if (!x_axis_label) {
            xlabel = plot_descr.xlabel;
            if (xunit.unit) xlabel += ' (' + unicode_unit(unit, xunit.exponent) + ')';

            x_axis_label = new Plottable.Components.Label(xlabel)
                .yAlignment("center");
        }
        if (!y_axis_label) {
            ylabel = plot_descr.ylabel;
            if (yunit.unit) ylabel += ' (' + unicode_unit(unit, yunit.exponent) + ')';

            y_axis_label = new Plottable.Components.Label(ylabel)
                .xAlignment("center")
                .angle(-90);
        }

        plot_descr.series.forEach(function (item) {
            var legend_str = plot_name;
            if (plot_descr.series.length > 1)  legend_str += ': ' + item.name;

            var style = item.style ? item.style : 'k-';

            var dataset = new Plottable.Dataset(
                item.y.map(function (value, index) {
                    return {x: scale_factor_x * this[index], y: scale_factor_y * value};
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
                else if (c in symbol_abbreviations) {
                    symbol = symbol_abbreviations[c];
                }
                else {
                    throw TypeError('Cannot interpret style string: ' + style);
                }
            }

            symbol = Object.values(symbol_abbreviations)[Object.values(plots).length % Object.values(symbol_abbreviations).length];

            if (line && item.y.length > 20) symbol = undefined;

            var plot_with_lines, plot_with_symbols;
            if (line) {
                plot_with_lines = new Plottable.Plots.Line()
                    .deferredRendering(true)
                    .addDataset(dataset)
                    .x((d) => d.x, x_scale)
                    .y((d) => d.y, y_scale)
                    .attr('stroke', legend_str, color_scale);
            }
            if (symbol) {
                plot_with_symbols = new Plottable.Plots.Scatter()
                    .deferredRendering(true)
                    .addDataset(dataset)
                    .x((d) => d.x, x_scale)
                    .y((d) => d.y, y_scale)
                    .symbol(() => symbol)
                    .attr('stroke', 'black').attr('fill', legend_str, color_scale);
            }
            plots[legend_str] = [plot_with_lines, plot_with_symbols];
        });
    }

    /* Create axes. */
    x_axis = new Plottable.Axes.Numeric(x_scale, "bottom")
        .formatter(Plottable.Formatters.exponential());
    y_axis = new Plottable.Axes.Numeric(y_scale, "left")
        .formatter(Plottable.Formatters.exponential());

    var legend = new Plottable.Components.Legend(color_scale)
        .symbol(function (datum) {
            s = symbols[datum];
            return s ? s : Plottable.SymbolFactories.circle();
        })
        .maxEntriesPerRow(3);

    var legend_interaction = new Plottable.Interactions.Click();
    legend_interaction.onClick(function (point) {
        var datum = legend.entitiesAt(point)[0].datum;
        for (var plot of plots[datum]) {
            if (plot) {
                var sel = plot.selections();
                if (sel.attr("visibility") == "hidden") {
                    sel.attr("visibility", "visible");
                }
                else {
                    sel.attr("visibility", "hidden");
                }
            }
        }
        legend.symbolOpacity(function (datum) {
            for (var plot of plots[datum]) {
                if (plot) {
                    if (plot.selections().attr("visibility") == "hidden") {
                        return .3;
                    }
                    else {
                        return 1;
                    }
                }
            }
        });
    });
    legend_interaction.attachTo(legend);

    var plot_group = new Plottable.Components.Group([].concat(...Object.values(plots)).filter(x => x));
    var chart = new Plottable.Components.Table([
        [null, null, legend],
        [y_axis_label, y_axis, plot_group],
        [null, null, x_axis, null],
        [null, null, x_axis_label, null]
    ]);

    var panZoom = new Plottable.Interactions.PanZoom(x_scale, y_scale)
        .attachTo(chart);

    chart.renderTo(element);
    $(element).width('100%');
    $(element).height('400px');
    chart.redraw();

    $(element).data('chart', chart);

    //panZoom.setMinMaxDomainValuesTo(x_scale);
    //panZoom.setMinMaxDomainValuesTo(y_scale);
}


/*
 * Updated scatter plot for a certain task. Continually poll task results if data not yet available.
 */
function plot(element, unit) {
    /* Show spinner. */
    $('.spinner', $(element).parent()).show();

    /* Enumerate all data request URLs into a single array. */
    var requests = $(element).data('src').map(url => $.get(url));

    done_func = function (element, ...data_array) {
        /* Loop over all data dictionaries and see if calculations have finished or failed. */
        for (var data of data_array) {
            /* Each data entry contains the JSON dictionary plus textStatus and jqHDR entries. */
            data = data[0];

            /* Check if task is PEnding or has STarted. */
            if (data.task_state == 'pe' || data.task_state == 'st') {
                setTimeout(function () {
                    plot(element, unit);
                }, 1000);
                return;
            }
            else {
                if ('error' in data.result) {
                    $(element).html('Server reported error: ' + data.result.error);
                    return;
                }
            }
        }

        /* Render plot. */
        render_plot(element,
                    data_array.map(data => data[0].topography_name),
                    data_array.map(data => data[0].result),
                    unit);
        $('.spinner', $(element).parent()).hide();
    };

    /* AJAX requests to all URLs in parallel. */
    $.when(...requests)
        .done(requests.length == 1 ?
                x => done_func(element, [x]) : function (...data_array) { done_func(element, ...data_array) })
        .fail(function () {
            $(element).html('Failed obtaining resources from server.');
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

    /* === VISUALIZATION === */

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

    /* Change units. */
    $('.topobank-change-unit').on('click', function (e) {
        /* Extract unit string from dropdown text. */
        t = $(this).html()
        unit = t.slice(t.length - 2, t.length);

        /* Trigger refresh of plot. */
        plot($('.topobank-scatter-plot', $(this).closest('.card')), unit);

        e.preventDefault();
    });
});

<script setup>
/*
 * Vue component that wraps a Bokeh plot and adds elements for controlling that plots appearance.
 * - Categories: Each dataset can be assigned multiple *categories*. Each category receives an accordion that allows to
 *   show/hide all datasets belonging to a specific value of this category. These categories are for example the names
 *   of a measurement and the data series (1D PSD, 2D PSD, etc.).
 */

import {v4 as uuid4} from 'uuid';
import {onMounted, ref, watch} from "vue";

import {
    AjaxDataSource,
    Circle,
    CustomJS,
    CustomJSTickFormatter,
    HoverTool,
    Legend,
    LegendItem,
    Plotting,
    SaveTool,
    TapTool
} from '@bokeh/bokehjs';

import {
    BAccordion,
    BAccordionItem,
    BFormCheckboxGroup,
    BFormGroup,
    BFormInput,
    BFormSelect,
    BFormSelectOption
} from "bootstrap-vue-next";

import {formatExponential} from "topobank/utils/formatting";
import {applyDefaultBokehStyle} from "topobank/utils/bokeh";

const emit = defineEmits([
    'selected'
]);

const props = defineProps({
    categories: {
        // Defining selection categories. For each category, there will be an accordion with the possibility to show/hide
        // all curves that correspond to a specific value of that category.
        // Array of dictionaries with keys:
        //   key: Name of dataset key that defines this category, i.e. if we have added a category with key "series_name",
        //        the code will expect a "series_name" key in a dataSource, that specifies the value for this category.
        //        Typical categories: "subject_name" for name of a measurement, "series_name" for name of a data series
        //        like "1D PSD along x"
        //   title: Title of this category, a header put in front of the category elements e.g. "Data Series"
        type: Array, default() {
            return [];
        }
    },
    plots: {
        // Define the plots to show. Each plot will display in its own tab if there is more than one.
        type: Array, default() {
            return [{
                title: "default",  // Title will be used to distinguish between multiple plots. Can be omitted for single plot.
                xData: "data.x",  // JS code that yields x data
                yData: "data.y",  // JS code that yields y data
                auxiliaryDataColumns: undefined,  // Auxiliary data columns
                alphaData: undefined,  // JS code that yields alpha information
                xAxisType: "linear",  // "log" or "linear"
                yAxisType: "linear",  // "log" or "linear"
                xAxisLabel: "x", // Label for the x-axis.
                yAxisLabel: "y" // Label for the y-axis.
            }]
        }
    },
    dataSources: {
        // Define the data sources.
        type: Array, default() {
            return [];
        }
        // Array of dictionaries with keys:
        //   url: URL to JSON that contains the data.
        //   [category-name] (optional): Display value of the specific category. For each category,
        //                               there must be a key-value pair. Example: "series_name": "1D PSD along x"
        //   [category-name]_index (optional): Zero-based index of [category_name] in an ordered list.
        //   color (optional): Line and symbol color.
        //   dash (optional): Line style, one of "solid", "dashed", "dotted", "dotdash", "dashdot".
        //   xScaleFactor: Additional scale factor for x-values from this source
        //   yScaleFactor: Additional scale factor for y-values from this source
        //   showSymbols (optional): Show symbols for this data source?
        //   visible (optional): Initial visibility (can be triggered by user).
        // Each data source is a JSON that is loaded from the given URL with via an AJAX request. The "plots"
        // property specifies for each plot, which JSON keys should be used to get x and y data.
    },
    outputBackend: String,
    height: {type: Number, default: 300},
    width: {type: Number, default: null},
    sizingMode: {type: String, default: "scale_width"},
    aspectRatio: {type: Number, default: 2},
    uid: {
        type: String, default() {
            return uuid4();
        }
    },
    selectable: {type: Boolean, default: false},
    optionsWidgets: {
        type: Array, default: function () {
            return ["layout", "legend", "lineWidth", "symbolSize", "opacity"];
        }
    },
    functionTitle: {type: String, default: "bokeh_plot"}
});

// GUI logic
const layout = ref("web");
const legendLocation = ref("off");
const symbolSize = ref(10);
const opacity = ref(0.4);
const lineWidth = ref(1);

// Reorganized plot information
const categoryElements = ref([]);
const bokehFigures = ref([]);  // Stores Bokeh figure, line and symbol objects

onMounted(() => {
    if (props.dataSources.length > 0) {
        updateCategoryElements();
        createFigures();
        createPlots();
    }
});

watch(layout, (layout) => {
    /* Predefined layouts */
    switch (layout) {
        case 'web':
            for (const plot of bokehFigures) {
                plot.figure.sizing_mode = props.sizingMode;
                plot.figure.aspect_ratio = props.aspectRatio;
                plot.figure.height = props.height;
            }
            symbolSize.value = 10;
            break;
        case 'print-single':
            for (const plot of bokehFigures) {
                plot.figure.sizing_mode = "fixed";
                plot.figure.width = 600;
                plot.figure.height = 300;
            }
            symbolSize.value = 5;
            break;
        case 'print-double':
            for (const plot of bokehFigures) {
                plot.figure.sizing_mode = "fixed";
                plot.figure.width = 400;
                plot.figure.height = 250;
            }
            symbolSize.value = 5;
            break;
    }

    refreshPlots();
});

watch(opacity, () => {
    refreshPlots();
});

watch(symbolSize, () => {
    refreshPlots();
});

watch(lineWidth, () => {
    refreshPlots();
});

watch(legendLocation, (newVal) => {
    const visible = newVal !== "off";
    for (const bokehPlot of bokehFigures) {
        bokehPlot.legend.visible = visible;
        if (visible) {
            bokehPlot.legend.location = newVal;
        }
    }
});

watch(props.dataSources, (newVal, oldVal) => {
    // For some unknown reason, the dataSource watch is triggered even though it is not updated. We have to check
    // manually that the URL has changed.
    let hasChanged = newVal.length !== oldVal.length;
    if (!hasChanged) {
        for (const [index, val] of newVal.entries()) {
            hasChanged = hasChanged || (val.url !== oldVal[index].url);
        }
    }
    // We need to completely rebuild the plot if `dataSources` changes
    if (hasChanged) {
        updateCategoryElements();
        if (bokehFigures.value.length === 0) {
            // Figures have not yet been created on mount because not data source was available, do it now.
            // We don't create empty figures because this screws up log scaling.
            createFigures();
        }
        createPlots();
    }
});

function legendLabel(dataSource) {
    /* Find number of selected items in second category (e.g. "series_name") */
    let secondCategoryInLegendLabels = false;
    if ((categoryElements.value.length > 1) && (categoryElements.value[1].selection.length > 1)) {
        secondCategoryInLegendLabels = true;
    }

    /* Find a label for the legend */
    let legendLabel = dataSource.source_name;
    if (dataSource.legendLabel !== undefined) {
        legendLabel = dataSource.legendLabel;
    } else if (props.categories.length > 0) {
        legendLabel = dataSource[props.categories[0].key];
        const hasParentKey = "hasParent";
        if ((dataSource[hasParentKey] !== undefined) && (dataSource[hasParentKey] === true) && !secondCategoryInLegendLabels) {
            legendLabel = "└─ " + legendLabel;
            /* It is not solved yet to get the legend items in the correct order
               to display sublevels only for the correct data series and not for others,
               and at the same time have the same colors and dashed for same subjects
               over different analysis functions. So we decided to remove the sublevels
               in legend if a second data series has been selected
               (here: More than one element selected in second category).
            */

        }
        if (secondCategoryInLegendLabels) {
            legendLabel += ": " + dataSource[props.categories[1].key];
        }
    }

    // console.log("this.categoryElements[1].selection: " + this.categoryElements[1].selection);
    // console.log(secondCategoryInLegendLabels, legendLabel);
    return legendLabel;
}

function updateCategoryElements() {
    // Reset the category elements array
    categoryElements.value.length = 0;

    /* For each category, create a list of unique entries */
    for (const [categoryIdx, category] of props.categories.entries()) {
        let titles = new Set();
        let elements = [];
        let selection = [];

        // console.log(`Category ${categoryIdx}: ${category.title} (key: ${category.key})`);
        // console.log("===============================================================");

        for (const dataSource of props.dataSources) {
            // console.table(dataSource);
            if (!(category.key in dataSource)) {
                throw new Error("Key '" + category.key + "' not found in data source '" + dataSource.name + "'.");
            }

            const title = dataSource[category.key];
            if (!(titles.has(title))) {
                let elementIndex = dataSource[category.key + 'Index'];
                let color = categoryIdx === 0 ? dataSource.color : null;  // The first category defines the color
                let dash = categoryIdx === 1 ? dataSource.dash : null;     // The first category defines the line type
                let hasParent = dataSource[category.key + 'HasParent'];
                titles.add(title);

                // need to have the same order as index of category
                elements[elementIndex] = {
                    title: title, color: color, dash: dash,
                    hasParent: hasParent === undefined ? false : hasParent
                };
                // Defaults to showing a data source if it has no 'visible' attribute
                if (dataSource.visible === undefined || dataSource.visible) {
                    selection.push(elementIndex);
                }
            }
        }

        const elementHtml = function (e) {
            let s = "";
            if (e.color !== null) {
                s += `<span class="dot" style="background-color: ${e.color};"></span>`;
            }
            if (e.hasParent) {
                s += "└─ ";
            }
            s += e.title;
            return s;
        };

        // Removed undefined entries from elements array
        elements = elements.filter(e => e !== undefined).map((e, index) => {
            return {
                ...e,
                value: index,
                html: elementHtml(e)
            }
        });

        // Add to category information
        categoryElements.value.push({
            key: category.key,
            title: category.title,
            elements: elements,
            selection: selection,
            isAllSelected: isAllSelected(elements, selection),
            isIndeterminate: isIndeterminate(elements, selection)
        });
    }
}

function createFigures() {
    /* Create figures */
    for (const plot of props.plots) {
        /* Callback for selection of data points */
        let tools = ["pan", "reset", "wheel_zoom", "box_zoom",
            new HoverTool({
                'tooltips': [
                    ['index', '$index'],
                    ['(x,y)', '($x,$y)'],
                    ['subject', '@subjectName'],
                    ['series', '@seriesName'],
                ]
            })
        ];
        // let tools = [...this.tools];  // Copy array (= would just be a reference)
        if (props.selectable) {
            const code = "on_tap(cb_obj, cb_data);";
            tools.push(new TapTool({
                behavior: "select",
                callback: new CustomJS({
                    args: {on_tap: onTap},
                    code: code
                })
            }));
        }
        const saveTool = new SaveTool({filename: props.functionTitle.replace(" ", "_").toLowerCase()});
        tools.push(saveTool);

        /* Determine type of x and y-axis */
        const xAxisType = plot.xAxisType === undefined ? "linear" : plot.xAxisType;
        const yAxisType = plot.yAxisType === undefined ? "linear" : plot.yAxisType;

        /* Create and style figure */
        const bokehFigure = new Plotting.Figure({
            height: props.height,
            sizing_mode: props.sizingMode,
            aspect_ratio: props.aspectRatio,
            x_axis_label: plot.xAxisLabel === undefined ? "x" : plot.xAxisLabel,
            y_axis_label: plot.yAxisLabel === undefined ? "y" : plot.yAxisLabel,
            x_axis_type: xAxisType,
            y_axis_type: yAxisType,
            tools: tools,
            output_backend: props.outputBackend
        });

        /* Change formatters for linear axes */
        if (xAxisType === "linear") {
            bokehFigure.xaxis.formatter = new CustomJSTickFormatter({
                code: "return formatExponential(tick);",
                args: {
                    formatExponential: formatExponential  // inject formatting function into local scope
                }
            });
        }
        if (yAxisType === "linear") {
            bokehFigure.yaxis.formatter = new CustomJSTickFormatter({
                code: "return formatExponential(tick);",
                args: {
                    formatExponential: formatExponential  // inject formatting function into local scope
                }
            });
        }

        /* This should become a Bokeh theme (supported in BokehJS with 3.0 - but I cannot find the `use_theme` method) */
        applyDefaultBokehStyle(bokehFigure);

        bokehFigures.value.push({
            figure: bokehFigure,
            save: saveTool,
            lines: [],
            symbols: [],
            sources: [],
            legendItems: []
        });
    }

    for (const [index, bokehFigure] of bokehFigures.value.entries()) {
        bokehFigure.legend = new Legend({items: bokehFigure.legendItems, visible: false});
        bokehFigure.figure.add_layout(bokehFigure.legend);
        Plotting.show(bokehFigure.figure, `#bokeh-figure-${props.uid}-${index}`);
    }
}

function createPlots() {
    /* Destroy all lines */
    for (const bokehFigure of bokehFigures.value) {
        bokehFigure.lines.length = 0;
        bokehFigure.symbols.length = 0;
        bokehFigure.figure.renderers.length = 0;
    }

    /* We iterate in reverse order because we want to the first element to appear on top of the plot */
    for (const dataSource of [...props.dataSources].reverse()) {
        for (const [index, plot] of props.plots.entries()) {
            /* Get bokeh plot object */
            const bokehPlot = bokehFigures.value[index];
            let legendLabels = new Set();

            /* Common attributes of lines and symbols */
            let attrs = {
                visible: dataSource.visible,
                color: dataSource.color,
                alpha: dataSource.isTopographyAnalysis ? Number(opacity.value) : dataSource.alpha
            };

            /* Default is x and y */
            let xData = plot.xData === undefined ? "data.x" : plot.xData;
            let yData = plot.yData === undefined ? "data.y" : plot.yData;

            /* Scale data if scale factor is given */
            if (dataSource.xScaleFactor !== undefined) {
                xData += ".map((value) => " + dataSource.xScaleFactor + " * value)";
            }
            if (dataSource.yScaleFactor !== undefined) {
                yData += ".map((value) => " + dataSource.yScaleFactor + " * value)";
            }

            /* Construct conversion function */
            let code = "const data = cb_data.response; return { x: " + xData + ", y: " + yData;
            if (plot.auxiliaryDataColumns !== undefined) {
                for (const [columnName, auxData] of Object.entries(plot.auxiliaryDataColumns)) {
                    code += ", " + columnName + ": " + auxData;
                }
            }
            if (plot.alphaData !== undefined) {
                code += ", alpha: " + plot.alphaData;
                attrs.alpha = {field: "alpha"};
            }
            if (dataSource.subjectName !== undefined) {
                // For each data point, add the same subject_name
                code += ", subjectName: " + xData + ".map((value) => '" + dataSource.subjectName + "')";
            }
            let seriesName = "-";
            if (dataSource.seriesName !== undefined) {
                seriesName = dataSource.seriesName;
            }
            // For each data point, add the same seriesName
            code += ", seriesName: " + xData + ".map((value) => '" + seriesName + "')";
            code += " }";

            /* Data source: AJAX GET request to storage system retrieving a JSON */
            const source = new AjaxDataSource({
                name: dataSource.sourceName,
                data_url: dataSource.url,
                method: "GET",
                content_type: "",
                syncable: false,
                adapter: new CustomJS({code})
            });
            bokehPlot.sources.unshift(source);

            /* Add data source */
            attrs = {
                ...attrs,
                source: source,
            };

            /* Create lines and symbols */
            const line = bokehPlot.figure.line(
                {field: "x"},
                {field: "y"},
                {
                    ...attrs,
                    ...{
                        dash: dataSource.dash,
                        width: Number(lineWidth.value) * dataSource.width
                    }
                });
            bokehPlot.lines.unshift(line);
            const circle = bokehPlot.figure.circle(
                {field: "x"},
                {field: "y"},
                {
                    ...attrs,
                    ...{
                        size: Number(symbolSize.value),
                        visible: (dataSource.visible === undefined || dataSource.visible) &&
                            (dataSource.showSymbols === undefined || dataSource.showSymbols)
                    }
                });
            const alphaAttrs = {};
            if (plot.alphaData !== undefined) {
                alphaAttrs.fill_alpha = {field: "alpha"};
            }
            circle.selection_glyph = new Circle({
                ...alphaAttrs,
                ...{
                    fill_color: attrs.color,
                    line_color: "black",
                    line_width: 4
                }
            });
            circle.nonselection_glyph = new Circle({
                ...alphaAttrs,
                ...{
                    fill_color: attrs.color,
                    line_color: null
                }
            });
            bokehPlot.symbols.unshift(circle);

            let label = legendLabel(dataSource);

            /* Create legend */
            if (!legendLabels.has(label)) {
                legendLabels.add(label);
                const item = new LegendItem({
                    label: label,
                    renderers: dataSource.showSymbols ? [circle, line] : [line],
                    visible: dataSource.visible
                });
                bokehPlot.legendItems.unshift(item);
                dataSource.legendItem = item;  // for toggling visibility
            }
        }
    }
}

function refreshPlots() {
    for (const [dataSourceIdx, dataSource] of props.dataSources.entries()) {
        let visible = true;
        for (const categoryElem of categoryElements.value) {
            visible = visible && categoryElem.selection.includes(dataSource[categoryElem.key + 'Index']);
        }

        if (dataSource.hasOwnProperty('legendItem')) {
            dataSource.legendItem.visible = visible;
            dataSource.legendItem.label = legendLabel(dataSource);
        }

        for (const bokehPlot of bokehFigures.value) {
            const line = bokehPlot.lines[dataSourceIdx];
            line.visible = visible;
            line.glyph.line_width = Number(lineWidth.value) * dataSource.width;
            if (dataSource.isTopographyAnalysis) {
                line.glyph.line_alpha = Number(opacity.value);
            }

            const symbol = bokehPlot.symbols[dataSourceIdx];
            symbol.visible = visible && (dataSource.showSymbols === undefined || dataSource.showSymbols);
            symbol.glyph.size = Number(symbolSize.value);
            if (dataSource.isTopographyAnalysis) {
                symbol.glyph.line_alpha = Number(opacity.value);
                symbol.glyph.fill_alpha = Number(opacity.value);
            }
        }
    }
    for (const categoryElem of categoryElements.value) {
        categoryElem.isAllSelected = isAllSelected(categoryElem.elements, categoryElem.selection);
        categoryElem.isIndeterminate = isIndeterminate(categoryElem.elements, categoryElem.selection);
    }
}

function isAllSelected(elements, selection) {
    return elements.length === selection.length;
}

function isIndeterminate(elements, selection) {
    return selection.length !== elements.length && selection.length !== 0;
}

function selectAll(category) {
    if (category.isAllSelected) {
        category.selection = [...Array(category.elements.length).keys()];
    } else {
        category.selection = [];
    }
}

function onTap(obj, data) {
    /* Make sure only the selection for one topography is active
       and deselect all others */
    const name = data.source.name;
    const index = data.source.selected.indices[0];
    for (const bokehPlot of bokehFigures.value) {
        for (const source of bokehPlot.sources) {
            if (source.name === name) {
                source.selected.indices = [index];
            }
        }
    }

    /* Emit event */
    emit("selected", obj, data);
}

function download() {
    bokehFigures.value[0].save.do.emit();
}

</script>

<template>
    <div class="tab-content">
        <div v-for="(plot, index) in plots" :class="(index == 0)?'tab-pane fade show active':'tab-pane fade'"
             :id="`plot-${uid}-${index}`" role="tabpanel" :aria-labelledby="`plot-tab-${uid}-${index}`">
            <div :id="`bokeh-figure-${uid}-${index}`" ref="plot"></div>
        </div>
    </div>
    <div v-if="plots.length > 1" class="card mb-2">
        <div class="card-body plot-controls-card-header">
            <h6 class="m-1">
                <!-- Navigation pills for each individual plot, but only if there is more than one -->
                <ul v-if="plots.length > 1" class="nav nav-pills">
                    <li v-for="(plot, index) in plots" class="nav-item">
                        <a :class="(index == 0)?'nav-link active':'nav-link'" :id="'plot-tab-'+uid+'-'+index"
                           :href="`#plot-${uid}-${index}`" data-toggle="tab" role="tab"
                           :aria-controls="`plot-${uid}-${index}`"
                           :aria-selected="index == 0">{{
                                plot.title
                            }}</a>
                    </li>
                </ul>
            </h6>
        </div>
    </div>
    <b-accordion>
        <b-accordion-item v-for="category in categoryElements"
                          :title="category.title">
            <b-form-checkbox-group v-model="category.selection"
                                   :options="category.elements"
                                   stacked/>
        </b-accordion-item>
        <b-accordion-item title="Plot options">
            <b-form-group v-if="optionsWidgets.includes('layout')"
                          label="Plot layout"
                          label-cols="4"
                          content-cols="8">
                <b-form-select v-model="layout">
                    <b-form-select-option value="web">
                        Optimize plot for web (plot scales with window size)
                    </b-form-select-option>
                    <b-form-select-option value="print-single">
                        Optimize plot for print (single-column layout)
                    </b-form-select-option>
                    <b-form-select-option value="print-double">
                        Optimize plot for print (two-column layout)
                    </b-form-select-option>
                </b-form-select>
            </b-form-group>

            <b-form-group v-if="optionsWidgets.includes('legend')"
                          label="Legend"
                          label-cols="4"
                          content-cols="8">
                <b-form-select v-model="legendLocation">
                    <b-form-select-option value="off">Do not show legend</b-form-select-option>
                    <b-form-select-option value="top_right">Show legend top right</b-form-select-option>
                    <b-form-select-option value="top_left">Show legend top left</b-form-select-option>
                    <b-form-select-option value="bottom_right">Show legend bottom right</b-form-select-option>
                    <b-form-select-option value="bottom_left">Show legend bottom left</b-form-select-option>
                </b-form-select>
            </b-form-group>

            <b-form-group v-if="optionsWidgets.includes('lineWidth')"
                          label="Line width"
                          label-cols="4"
                          content-cols="8">
                <b-form-input type="range"
                              min="0.1"
                              max="3.0"
                              step="0.1"
                              v-model="lineWidth"/>
            </b-form-group>

            <b-form-group v-if="optionsWidgets.includes('symbolSize')"
                          label="Symbol size"
                          label-cols="4"
                          content-cols="8">
                <b-form-input type="range"
                              min="1"
                              max="20"
                              step="1"
                              v-model="symbolSize"/>
            </b-form-group>

            <b-form-group v-if="optionsWidgets.includes('opacity')"
                          label="Opacity of lines/symbols (measurements only)"
                          label-cols="4"
                          content-cols="8">
                <b-form-input type="range"
                              min="0"
                              max="1"
                              step="0.1"
                              v-model="opacity"/>
            </b-form-group>
        </b-accordion-item>
    </b-accordion>
</template>

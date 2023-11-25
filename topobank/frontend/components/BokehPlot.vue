<script setup>
/*
 * Vue component that wraps a Bokeh plot and adds elements for controlling that plots appearance.
 * - Categories: Each dataset can be assigned multiple *categories*. Each category receives an accordion that allows to
 *   show/hide all datasets belonging to a specific value of this category. These categories are for example the names
 *   of a measurement and the data series (1D PSD, 2D PSD, etc.).
 */

import {v4 as uuid4} from 'uuid';
import {computed, onMounted, ref, watch} from "vue";

import {
    AjaxDataSource,
    Circle,
    CustomJS,
    CustomJSTickFormatter,
    HoverTool,
    Legend,
    LegendItem,
    Palettes,
    Plotting,
    SaveTool,
    TapTool
} from '@bokeh/bokehjs';

import {
    BAccordion,
    BAccordionItem,
    BFormCheckbox,
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
    showSymbols: {type: Boolean, default: true},
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
const _layout = ref("web");
const _legendLocation = ref("off");
const _symbolSize = ref(10);
const _opacity = ref(0.4);
const _lineWidth = ref(1);

// Reorganized plot information
let _bokehFigures = [];  // Stores Bokeh figure, line and symbol objects
let _categoryElements = ref([]);  // Sorted categories with selectable elements
let _categoryElementSelections = [];  // Flags which categories are selected

// Colors
const _parentColorPalette = Palettes.Greys256;  // Surfaces are shown in black/grey
const _childColorPalette = Palettes.Plasma256;  // Plasma is used for topographies
const _dashes = ['solid', 'dashed', 'dotted', 'dotdash', 'dashdot'];

onMounted(() => {
    if (props.dataSources.length > 0) {
        /* We only create figures if data sources are present. If they are not present, we defer creation of the figure
           to that point. The reason is that if we create an empty plot, the log-scaled axes do not work. */
        createFigures();
        /* Create a matrix of categories/elements and assign colors and line styles */
        updateCategoryElements();
        /* Create plots */
        createPlots();
    }
});

watch(_layout, (layout) => {
    /* Predefined layouts */
    switch (layout) {
        case 'web':
            for (const figure of _bokehFigures) {
                figure.figure.sizing_mode = props.sizingMode;
                figure.figure.aspect_ratio = props.aspectRatio;
                figure.figure.height = props.height;
            }
            _symbolSize.value = 10;
            break;
        case 'print-single':
            for (const figure of _bokehFigures) {
                figure.figure.sizing_mode = "fixed";
                figure.figure.width = 600;
                figure.figure.height = 300;
            }
            _symbolSize.value = 5;
            break;
        case 'print-double':
            for (const figure of _bokehFigures) {
                figure.figure.sizing_mode = "fixed";
                figure.figure.width = 400;
                figure.figure.height = 250;
            }
            _symbolSize.value = 5;
            break;
    }

    refreshPlots();
});

watch(_opacity, () => {
    refreshPlots();
});

watch(_symbolSize, () => {
    refreshPlots();
});

watch(_lineWidth, () => {
    refreshPlots();
});

watch(_legendLocation, (newVal) => {
    const visible = newVal !== "off";
    for (const figure of _bokehFigures) {
        figure.legend.visible = visible;
        if (visible) {
            figure.legend.location = newVal;
        }
    }
});

// Watching props, see here: https://stackoverflow.com/questions/59125857/how-to-watch-props-change-with-vue-composition-api-vue-3
watch(() => props.dataSources, (newVal, oldVal) => {
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
        if (_bokehFigures.length === 0) {
            /* Figures have not yet been created on mount because not data source was available, do it now.
               We don't create empty figures because this screws up log scaling. */
            createFigures();
        }
        /* Create a matrix of categories/elements and assign colors and line styles */
        updateCategoryElements();
        /* Update all plots */
        createPlots();
    }
});

function legendLabel(dataSource) {
    /* Find number of selected items in second category (e.g. "series_name") */
    let secondCategoryInLegendLabels = false;

    /* Find a label for the legend */
    let legendLabel = dataSource.source_name;
    if (dataSource.legendLabel !== undefined) {
        legendLabel = dataSource.legendLabel;
    } else if (props.categories.length > 0) {
        legendLabel = dataSource[props.categories[0].key];
        const hasParentKey = "hasParent";
        if ((dataSource[hasParentKey] != null) && (dataSource[hasParentKey] === true) && !secondCategoryInLegendLabels) {
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
    // Reset selection array
    _categoryElementSelections = [];

    // Reset the category elements array
    _categoryElements.value.length = 0;

    /* For each category, create a list of unique entries */
    for (const [categoryIndex, category] of props.categories.entries()) {
        let elements = [];
        let selections = [];

        for (const dataSource of props.dataSources) {
            if (!(category.key in dataSource)) {
                throw new Error("Key '" + category.key + "' not found in data source '" + dataSource.name + "'.");
            }

            const title = dataSource[category.key];
            let elementIndex = dataSource[category.key + 'Index'];
            let hasParent = dataSource[category.key + 'HasParent'];

            // Skip filling the arrays if they are already filled
            if (elements[elementIndex] != null) continue;

            // Need to have the same order as index of category
            elements[elementIndex] = {
                title: title, color: null, dash: null,
                hasParent: hasParent == null ? false : hasParent,
                selected: computed({
                    get() {
                        return _categoryElementSelections[categoryIndex][elementIndex].value;
                    },
                    set(value) {
                        setPlotVisibility(categoryIndex, elementIndex, value);
                        _categoryElementSelections[categoryIndex][elementIndex].value = value;
                    }
                })
            };

            // Defaults to showing a data source if it has no 'visible' attribute
            selections[elementIndex] = ref(dataSource.visible == null || dataSource.visible);
        }

        // Add empty selection array
        _categoryElementSelections.push(selections);

        // Add to category information
        _categoryElements.value.push({
            key: category.key,
            title: category.title,
            elements: elements
        });
    }

    /* Do we have any categories? */
    if (_categoryElements.value.length > 0) {
        /* Loop over elements of first category to count number of parent and child elements */
        let nbParents = 0;
        let nbChildren = 0;
        for (const element of _categoryElements.value[0].elements) {
            if (element.hasParent) {
                nbChildren++;
            } else {
                nbParents++;
            }
        }

        /* Loop over elements of first category to set color */
        let parentIndex = 0;
        let childIndex = 0;
        for (let element of _categoryElements.value[0].elements) {
            if (element.hasParent) {
                element.color = _childColorPalette[Math.trunc(childIndex * 256 / nbChildren)];
                childIndex++;
            } else {
                if (nbChildren === 0) {
                    element.color = _childColorPalette[Math.trunc(parentIndex * 256 / nbParents)];
                } else {
                    element.color = _parentColorPalette[Math.trunc(parentIndex * 256 / nbParents)];
                }
                parentIndex++;
            }
        }

        /* Loop over elements of second category to set dash */
        if (_categoryElements.value[1] != null) {
            for (let [elementIndex, element] of _categoryElements.value[1].elements.entries()) {
                element.dash = _dashes[elementIndex % _dashes.length];
            }
        }
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

        /* Add tap tool if item should be selectable */
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

        /* Add save tool, file name derives from function name */
        const saveTool = new SaveTool({filename: props.functionTitle.replace(" ", "_").toLowerCase()});
        tools.push(saveTool);

        /* Determine type of x and y-axis */
        const xAxisType = plot.xAxisType === undefined ? "linear" : plot.xAxisType;
        const yAxisType = plot.yAxisType === undefined ? "linear" : plot.yAxisType;

        /* Create and style figure */
        const figure = new Plotting.Figure({
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
            figure.xaxis.formatter = new CustomJSTickFormatter({
                code: "return formatExponential(tick);",
                args: {
                    formatExponential: formatExponential  // inject formatting function into local scope
                }
            });
        }
        if (yAxisType === "linear") {
            figure.yaxis.formatter = new CustomJSTickFormatter({
                code: "return formatExponential(tick);",
                args: {
                    formatExponential: formatExponential  // inject formatting function into local scope
                }
            });
        }

        /* This should become a Bokeh theme (supported in BokehJS with 3.0 - but I cannot find the `use_theme` method) */
        applyDefaultBokehStyle(figure);

        _bokehFigures.push({
            figure: figure,
            save: saveTool,
            lines: [],
            symbols: [],
            sources: [],
            legendItems: []
        });
    }

    for (const [index, figure] of _bokehFigures.entries()) {
        figure.legend = new Legend({items: figure.legendItems, visible: false});
        figure.figure.add_layout(figure.legend);
        Plotting.show(figure.figure, `#bokeh-figure-${props.uid}-${index}`);
    }
}

function createPlots() {
    /* Destroy all lines */
    for (const figure of _bokehFigures) {
        figure.lines.length = 0;
        figure.symbols.length = 0;
        figure.figure.renderers.length = 0;
    }

    /* Get first and second category (to decide on color and dash) */
    const firstCategory = props.categories[0];
    const secondCategory = props.categories[1];

    /* We iterate in reverse order because we want to the first element to appear on top of the plot */
    for (const dataSource of [...props.dataSources].reverse()) {
        /* Element indices */
        const firstElementIndex = firstCategory == null ? null : dataSource[firstCategory.key + 'Index'];
        const secondElementIndex = secondCategory == null ? null : dataSource[secondCategory.key + 'Index'];

        /* Get element */
        const firstElement = firstCategory == null ? null : _categoryElements.value[0].elements[firstElementIndex];
        const secondElement = secondCategory == null ? null : _categoryElements.value[1].elements[secondElementIndex];

        for (const [plotIndex, plot] of props.plots.entries()) {
            /* Get Bokeh plot object */
            const figure = _bokehFigures[plotIndex];
            let legendLabels = new Set();

            /* Common attributes of lines and symbols */
            let attrs = {
                visible: dataSource.visible,
                color: firstElement == null ? 'black' : firstElement.color,
                alpha: dataSource.isTopographyAnalysis ? Number(_opacity.value) : dataSource.alpha
            };

            /* Default is x and y as columns for the scatter plot */
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
            figure.sources.unshift(source);

            /* Add data source */
            attrs = {
                ...attrs,
                source: source,
            };

            let renderers = [];

            /* Create lines */
            const line = figure.figure.line(
                {field: "x"},
                {field: "y"},
                {
                    ...attrs,
                    ...{
                        dash: secondElement == null ? 'solid' : secondElement.dash,
                        width: Number(_lineWidth.value) * dataSource.width
                    }
                });
            figure.lines.unshift(line);
            renderers.push(line);

            /* Create symbols */
            if (props.showSymbols) {
                const symbolAttrs = {
                    ...attrs,
                    ...{
                        size: Number(_symbolSize.value),
                        visible: dataSource.visible == null || dataSource.visible,
                    }
                };
                let symbols = null;
                if (dataSource.hasParent) {
                    symbols = figure.figure.x(
                        {field: "x"},
                        {field: "y"},
                        symbolAttrs);
                } else {
                    symbols = figure.figure.circle(
                        {field: "x"},
                        {field: "y"},
                        symbolAttrs);
                }
                const alphaAttrs = {};
                if (plot.alphaData !== undefined) {
                    alphaAttrs.fill_alpha = {field: "alpha"};
                }
                symbols.selection_glyph = new Circle({
                    ...alphaAttrs,
                    ...{
                        fill_color: attrs.color,
                        line_color: "black",
                        line_width: 4
                    }
                });
                symbols.nonselection_glyph = new Circle({
                    ...alphaAttrs,
                    ...{
                        fill_color: attrs.color,
                        line_color: null
                    }
                });
                figure.symbols.unshift(symbols);

                renderers.push(symbols, line);
            }

            let label = legendLabel(dataSource);

            /* Create legend */
            if (!legendLabels.has(label)) {
                legendLabels.add(label);
                const item = new LegendItem({
                    label: label,
                    renderers: renderers,
                    visible: dataSource.visible
                });
                figure.legendItems.unshift(item);
                dataSource.legendItem = item;  // for toggling visibility
            }
        }
    }
}

function refreshPlots() {
    for (const [dataSourceIndex, dataSource] of props.dataSources.entries()) {
        for (const figure of _bokehFigures) {
            const line = figure.lines[dataSourceIndex];
            line.glyph.line_width = Number(_lineWidth.value) * dataSource.width;
            if (dataSource.isTopographyAnalysis) {
                line.glyph.line_alpha = Number(_opacity.value);
            }

            const symbol = figure.symbols[dataSourceIndex];
            symbol.glyph.size = Number(_symbolSize.value);
            if (dataSource.isTopographyAnalysis) {
                symbol.glyph.line_alpha = Number(_opacity.value);
                symbol.glyph.fill_alpha = Number(_opacity.value);
            }
        }
    }
}

function setPlotVisibility(categoryIndex, elementIndex, visible) {
    const category = props.categories[categoryIndex];
    const categoryKey = category.key + 'Index';
    for (const [dataSourceIndex, dataSource] of props.dataSources.entries()) {
        if (dataSource[categoryKey] === elementIndex) {
            let dataSourceVisible = visible;
            for (const [i, category] of props.categories.entries()) {
                if (i !== categoryIndex) {
                    const k = category.key + 'Index';
                    dataSourceVisible &&= _categoryElementSelections[i][dataSource[k]].value;
                }
            }
            for (const figure of _bokehFigures) {
                figure.lines[dataSourceIndex].visible = dataSourceVisible;
                figure.symbols[dataSourceIndex].visible = dataSourceVisible;
                figure.legendItems[dataSourceIndex].visible = dataSourceVisible;
            }
        }
    }
}

function onTap(obj, data) {
    /* Make sure only the selection for one topography is active
       and deselect all others */
    const name = data.source.name;
    const index = data.source.selected.indices[0];
    for (const bokehPlot of _bokehFigures) {
        for (const source of bokehPlot.sources) {
            if (source.name === name) {
                source.selected.indices = [index];
            }
        }
    }

    /* Emit event */
    emit("selected", obj, data);
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
                           :aria-selected="index == 0">
                            {{ plot.title }}
                        </a>
                    </li>
                </ul>
            </h6>
        </div>
    </div>
    <b-accordion>
        <b-accordion-item v-for="[categoryIndex, category] in _categoryElements.entries()"
                          :title="category.title">
            <b-form-checkbox v-for="element in category.elements"
                             v-model="element.selected">
                <span v-if="element.color != null"
                      class="dot" :style="`background-color: #${element.color.toString(16)}`"></span>
                <span v-if="element.hasParent">└─</span>
                {{ element.title }}
            </b-form-checkbox>
        </b-accordion-item>
        <b-accordion-item title="Plot options">
            <b-form-group v-if="optionsWidgets.includes('layout')"
                          label="Plot layout"
                          label-cols="4"
                          content-cols="8">
                <b-form-select v-model="_layout">
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
                <b-form-select v-model="_legendLocation">
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
                              v-model="_lineWidth"/>
            </b-form-group>

            <b-form-group v-if="optionsWidgets.includes('symbolSize')"
                          label="Symbol size"
                          label-cols="4"
                          content-cols="8">
                <b-form-input type="range"
                              min="1"
                              max="20"
                              step="1"
                              v-model="_symbolSize"/>
            </b-form-group>

            <b-form-group v-if="optionsWidgets.includes('opacity')"
                          label="Opacity of lines/symbols (measurements only)"
                          label-cols="4"
                          content-cols="8">
                <b-form-input type="range"
                              min="0"
                              max="1"
                              step="0.1"
                              v-model="_opacity"/>
            </b-form-group>
        </b-accordion-item>
    </b-accordion>
</template>

/*
 * Vue component that wraps a Bokeh plot and adds elements for controlling that plots appearance.
 * - Categories: Each dataset can be assigned multiple *categories*. Each category receives an accordion that allows to
 *   show/hide all datasets belonging to a specific value of this category. These categories are for example the names
 *   of a measurement and the data series (1D PSD, 2D PSD, etc.).
 */
/* jshint esversion: 9 */
/* jshint strict:true */
"use strict";
/* globals Vue:false, Bokeh:false */

Vue.component("bokeh-plot", {
  template: `
    <div>
      <div class="tab-content">
        <div v-for="(plot, index) in plots" :class="(index == 0)?'tab-pane fade show active':'tab-pane fade'" :id="'plot-'+uuid+'-'+index" role="tabpanel" :aria-labelledby="'plot-tab-'+uuid+'-'+index">
          <div :id='"bokeh-plot-"+uuid+"-"+index' ref="bokehPlot"></div>
        </div>
      </div>
      <div :id='"plot-controls-accordion-"+uuid' class="accordion plot-controls-accordion">
        <div v-if="plots.length > 1" class="card">
          <div class="card-header plot-controls-card-header">
            <h6 class="m-1">
              <!-- Navigation pills for each individual plot, but only if there is more than one -->
              <ul v-if="plots.length > 1" class="nav nav-pills">
                <li v-for="(plot, index) in plots" class="nav-item">
                  <a :class="(index == 0)?'nav-link active':'nav-link'" :id="'plot-tab-'+uuid+'-'+index" :href="'#plot-'+uuid+'-'+index" data-toggle="tab" role="tab" :aria-controls="'plot-'+uuid+'-'+index" :aria-selected="index == 0">{{ plot.title }}</a>
                </li>
              </ul>
            </h6>
          </div>
        </div>
        <div v-for="category in categoryElements" class="card">
          <div :id='"heading-"+uuid+"-"+category.key' class="card-header plot-controls-card-header">
            <h2 class="mb-0">
              <div class="accordion-header-control custom-checkbox">
                <input :id='"select-all-"+uuid+"-"+category.key'
                       class="custom-control-input"
                       type="checkbox"
                       value=""
                       v-model="category.isAllSelected"
                       v-on:change="selectAll(category)"
                       :indeterminate.prop="category.isIndeterminate">
                <label class="custom-control-label btn-block text-left"
                       :for='"select-all-"+uuid+"-"+category.key'>
                </label>
              </div>
              <button class="btn btn-link btn-block text-left accordion-button collapsed"
                      type="button"
                      data-toggle="collapse"
                      :data-target='"#collapse-"+uuid+"-"+category.key'
                      aria-expanded="false"
                      :aria-controls='"collapse-"+uuid+"-"+category.key'>
                {{ category.title }}
              </button>
            </h2>
          </div>
          <div :id='"collapse-"+uuid+"-"+category.key'
               class="collapse"
               :aria-labelledby='"heading-"+uuid+"-"+category.key'
               :data-parent='"#plot-controls-accordion-"+uuid'>
            <div :id='"card-subjects"+uuid' class="card-body plot-controls-card-body">
              <div v-for="(element, index) in category.elements" class="custom-control custom-checkbox">
                <input :id='"switch-"+uuid+"-"+category.key+"-"+index'
                       class="custom-control-input"
                       type="checkbox"
                       :value="index"
                       v-model="category.selection">
                <label class="custom-control-label"
                       :for='"switch-"+uuid+"-"+category.key+"-"+index'>
                  <span class="dot" v-if="element.color !== null" :style='"background-color: "+element.color'></span>
                  <span v-if="element.has_parent">└─ </span>
                    {{ element.title }}
                </label>
              </div>
            </div>
          </div>
        </div>
        <div class="card">
          <div :id='"heading-plot-options-"+uuid' class="card-header plot-controls-card-header">
            <h2 class="mb-0">
              <button class="btn btn-link btn-block text-left accordion-button collapsed"
                      type="button"
                      data-toggle="collapse"
                      :data-target='"#collapse-plot-options-"+uuid'
                      aria-expanded="false"
                      :aria-controls='"collapse-plot-options-"+uuid'>
                Plot options
              </button>
            </h2>
          </div>
          <div :id='"collapse-plot-options-"+uuid'
               class="collapse"
               :aria-labelledby='"heading-plot-options-"+uuid'
               :data-parent='"#plot-controls-accordion-"+uuid'>
            <div class="card-body plot-controls-card-body">
              <div v-if="optionsWidgets.includes('layout')" class="form-group">
                <label :for='"plot-layout-"+uuid' hidden>Plot layout:</label>
                <select class="form-control"
                       :id='"plot-layout-"+uuid'
                       v-model="layout">
                  <option value="web">Optimize plot for web (plot scales with window size)</option>
                  <option value="print-single">Optimize plot for print (single-column layout)</option>
                  <option value="print-double">Optimize plot for print (two-column layout)</option>
                </select>
              </div>

              <div v-if="optionsWidgets.includes('legend')" class="form-group">
                <label :for='"plot-legend-"+uuid' hidden>Legend:</label>
                <select class="form-control"
                       :id='"plot-legend-"+uuid'
                       v-model="legendLocation">
                  <option value="off">Do not show legend</option>
                  <option value="top_right">Show legend top right</option>
                  <option value="top_left">Show legend top left</option>
                  <option value="bottom_right">Show legend bottom right</option>
                  <option value="bottom_left">Show legend bottom left</option>
                </select>
              </div>

              <div v-if="optionsWidgets.includes('lineWidth')" class="form-group">
                <label :for='"line-width-slider-"+uuid'>Line width: <b>{{ lineWidth }}</b></label>
                <input :id='"line-width-slider-"+uuid'
                       type="range"
                       min="0.1"
                       max="3.0"
                       step="0.1"
                       class="form-control-range"
                       v-model="lineWidth">
              </div>

              <div v-if="optionsWidgets.includes('symbolSize')" class="form-group">
                <label :for='"symbol-size-slider-"+uuid'>Symbol size: <b>{{ symbolSize }}</b></label>
                <input :id='"symbol-size-slider-"+uuid'
                       type="range"
                       min="1"
                       max="20"
                       step="1"
                       class="form-control-range"
                       v-model="symbolSize">
              </div>

              <div v-if="optionsWidgets.includes('opacity')" class="form-group">
                <label :for='"opacity-slider-"+uuid'>Opacity of lines/symbols (measurements only): <b>{{ opacity }}</b></label>
                <input :id='"opacity-slider-"+uuid'
                       type="range"
                       min="0"
                       max="1"
                       step="0.1"
                       class="form-control-range"
                       v-model="opacity">
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `,
  props: {
    categories: {
      // Defining selection categories. For each category, there will be an accordion with the possibility to show/hide
      // all curves that correspond to a specific value of that category.
      // Array of dictionaries with keys:
      //   key: Name of dataset key that defines this category, i.e. if we have add a category with key "series_name",
      //        the code will expect a "series_name" key in a dataSource, that specifies the value for this category.
      //        Typical categories: "subject_name" for name of a measurement, "series_name" for name of a data series like
      //        "1D PSD along x"
      //   title: Title of this category, a header put in front of the category elements e.g. "Data Series"
      type: Array, default: function () {
        return [];
      }
    },
    plots: {
      // Define the plots to show. Each plot will display in its own tab if there is more than one.
      type: Array,
      default: [{
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
    },
    dataSources: {
      // Define the data sources.
      type: Array, default: []
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
    height: {
      type: Number, default: 300
    },
    width: {
      type: Number, default: null
    },
    sizingMode: {
      type: String, default: "scale_width"
    },
    tools: {
      type: Array, default: function () {
        return ["pan", "reset", "wheel_zoom", "box_zoom",
                new Bokeh.HoverTool({
                  'tooltips': [
                      ['index', '$index'],
                      ['(x,y)', '($x,$y)'],
                      ['subject', '@subject_name'],
                      ['series', '@series_name'],
                ]
                })
        ];
      }
    },
    selectable: {
      type: Boolean, default: false
    },
    optionsWidgets: {
      type: Array, default: function() {
        return ["layout", "legend", "lineWidth", "symbolSize", "opacity"];
      }
    }
  },
  data: function () {
    return {
      uuid: null,  // Unique identifier that is embedded in the HTML ids
      layout: "web",
      legendLocation: "off",
      symbolSize: 10,
      opacity: 0.4,
      lineWidth: 1,
      categoryElements: [],
      bokehPlots: [],  // Stores Bokeh figure, line and symbol objects
    };
  },
  created: function () {
    /* Create unique ID */
    this.uuid = crypto.randomUUID();

    /* For each category, create a list of unique entries */
    for (const [category_idx, category] of this.categories.entries()) {
      let titles = new Set();
      let elements = [];
      let selection = [];

      // console.log(`Category ${category_idx}: ${category.title} (key: ${category.key})`);
      // console.log("===============================================================");

      for (const dataSource of this.dataSources) {
        // console.table(dataSource);
        if (!(category.key in dataSource)) {
          throw new Error("Key '" + category.key + "' not found in data source '" + dataSource.name + "'.");
        }

        const title = dataSource[category.key];
        if (!(titles.has(title))) {
          let element_index = dataSource[category.key + '_index'];
          let color = category_idx === 0 ? dataSource.color : null;  // The first category defines the color
          let dash = category_idx ===1 ? dataSource.dash : null;     // The first category defines the line type
          let has_parent = dataSource[category.key + '_has_parent'];
          titles.add(title);

          // need to have the same order as index of category
          elements[element_index] = {
            title: title, color: color, dash: dash,
            has_parent: has_parent === undefined ? false:has_parent
          };
          // Defaults to showing a data source if it has no 'visible' attribute
          if (dataSource.visible === undefined || dataSource.visible) {
            selection.push(element_index);
          }
        }
      }

      this.categoryElements.push({
        key: category.key,
        title: category.title,
        elements: elements,
        selection: selection,
        isAllSelected: this.isAllSelected(elements, selection),
        isIndeterminate: this.isIndeterminate(elements, selection)
      });
    }
  },
  mounted: function () {
    this.buildPlot();
  },
  watch: {
    categoryElements: {
      handler: function () {
        this.refreshPlot();
      }, deep: true
    },
    layout: function (layout) {
      /* Predefined layouts */
      switch (layout) {
        case 'web':
          for (const plot of this.bokehPlots) {
            plot.figure.sizing_mode = "scale_width";
            plot.figure.width = null;
            plot.figure.height = 300;
          }
          this.symbolSize = 10;
          break;
        case 'print-single':
          for (const plot of this.bokehPlots) {
            plot.figure.sizing_mode = "fixed";
            plot.figure.width = 600;
            plot.figure.height = 300;
          }
          this.symbolSize = 5;
          break;
        case 'print-double':
          for (const plot of this.bokehPlots) {
            plot.figure.sizing_mode = "fixed";
            plot.figure.width = 400;
            plot.figure.height = 250;
          }
          this.symbolSize = 5;
          break;
      }

      this.refreshPlot();
    },
    opacity: function () {
      this.refreshPlot();
    },
    symbolSize: function () {
      this.refreshPlot();
    },
    lineWidth: function () {
      this.refreshPlot();
    },
    legendLocation: function (newVal) {
      const visible = newVal !== "off";
      for (const bokehPlot of this.bokehPlots) {
        bokehPlot.legend.visible = visible;
        if (visible) {
          bokehPlot.legend.location = newVal;
        }
      }
    },
    dataSources: function (newVal, oldVal) {
      // For some unknown reason, the dataSource watch is triggered even though it is not updated. We have to check
      // manually that the URL has changed.
      let has_changed = newVal.length !== oldVal.length;
      if (!has_changed) {
        for (const [index, val] of newVal.entries()) {
          has_changed = has_changed || (val.url !== oldVal[index].url);
        }
      }
      // We need to completely rebuild the plot if `dataSources` changes
      if (has_changed) {
        this.buildPlot();
      }
    }
  },
  methods: {
    legend_label(dataSource) {
      /* Find number of selected items in second category (e.g. "series_name") */
      let second_category_in_legend_labels = false;
      if ((this.categoryElements.length > 1) && (this.categoryElements[1].selection.length > 1)) {
        second_category_in_legend_labels = true;
      }

      /* Find a label for the legend */
      let legend_label = dataSource.source_name;
      if (dataSource.legend_label !== undefined) {
        legend_label = dataSource.legend_label;
      } else if (this.categories.length > 0) {
        legend_label = dataSource[this.categories[0].key];
        const has_parent_key = "has_parent";
        if ((dataSource[has_parent_key] !== undefined) && (dataSource[has_parent_key] === true) && !second_category_in_legend_labels) {
          legend_label = "└─ " + legend_label;
          /* It is not solved yet to get the legend items in the correct order
             to display sublevels only for the correct data series and not for others,
             and at the same time have the same colors and dashed for same subjects
             over different analysis functions. So we decided to remove the sublevels
             in legend if a second data series has been selected
             (here: More than one element selected in second category).
          */

        }
        if (second_category_in_legend_labels) {
          legend_label += ": " + dataSource[this.categories[1].key];
        }
      }

      // console.log("this.categoryElements[1].selection: " + this.categoryElements[1].selection);
      // console.log(second_category_in_legend_labels, legend_label);
      return legend_label;
    },
    buildPlot() {
      /* Destroy all lines */
      for (const bokehPlot of this.bokehPlots) {
        bokehPlot.lines.length = 0;
        bokehPlot.symbols.length = 0;
        bokehPlot.figure.renderers.length = 0;
      }

      const isNewPlot = this.bokehPlots.length === 0;
      if (isNewPlot) {
        /* Create figures */
        for (const plot of this.plots) {
          /* Callback for selection of data points */
          let tools = [...this.tools];  // Copy array (= would just be a reference)
          if (this.selectable) {
            const code = "self.onTap(cb_obj, cb_data);";
            tools.push(new Bokeh.TapTool({
              behavior: "select",
              callback: new Bokeh.CustomJS({
                args: {self: this},
                code: code
              })
            }));
          }
          const saveTool = new Bokeh.SaveTool();
          tools.push(saveTool);

          /* Determine type of x and y-axis */
          const xAxisType = plot.xAxisType === undefined ? "linear" : plot.xAxisType;
          const yAxisType = plot.yAxisType === undefined ? "linear" : plot.yAxisType;

          /* Create and style figure */
          const bokehPlot = new Bokeh.Plotting.Figure({
            height: this.height,
            sizing_mode: this.sizingMode,
            x_axis_label: plot.xAxisLabel === undefined ? "x" : plot.xAxisLabel,
            y_axis_label: plot.yAxisLabel === undefined ? "y" : plot.yAxisLabel,
            x_axis_type: xAxisType,
            y_axis_type: yAxisType,
            tools: tools,
            output_backend: this.outputBackend
          });

          /* Change formatters for linear axes */
          if (xAxisType === "linear") {
            bokehPlot.xaxis.formatter = new Bokeh.CustomJSTickFormatter({code: "return format_exponential(tick);"});
          }
          if (yAxisType === "linear") {
            bokehPlot.yaxis.formatter = new Bokeh.CustomJSTickFormatter({code: "return format_exponential(tick);"});
          }

          /* This should become a Bokeh theme (supported in BokehJS with 3.0 - but I cannot find the `use_theme` method) */
          bokehPlot.xaxis.axis_label_text_font_style = "normal";
          bokehPlot.yaxis.axis_label_text_font_style = "normal";
          bokehPlot.xaxis.major_label_text_font_size = "16px";
          bokehPlot.yaxis.major_label_text_font_size = "16px";
          bokehPlot.xaxis.axis_label_text_font_size = "16px";
          bokehPlot.yaxis.axis_label_text_font_size = "16px";

          this.bokehPlots.push({
            figure: bokehPlot,
            save: saveTool,
            lines: [],
            symbols: [],
            sources: [],
            legendItems: []
          });
        }
      }

      /* We iterate in reverse order because we want to the first element to appear on top of the plot */
      for (const dataSource of [...this.dataSources].reverse()) {
        for (const [index, plot] of this.plots.entries()) {
          /* Get bokeh plot object */
          const bokehPlot = this.bokehPlots[index];
          let legendLabels = new Set();

          /* Common attributes of lines and symbols */
          let attrs = {
            visible: dataSource.visible,
            color: dataSource.color,
            alpha: dataSource.alpha
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
          if (dataSource.subject_name !== undefined) {
            // For each data point, add the same subject_name
            code += ", subject_name: " + xData + ".map((value) => '" + dataSource.subject_name + "')";
          }
          let series_name = "-";
          if (dataSource.series_name !== undefined) {
            series_name = dataSource.series_name;
          }
          // For each data point, add the same series_name
          code += ", series_name: " + xData + ".map((value) => '" + series_name + "')";
          code += " }";

          /* Data source: AJAX GET request to storage system retrieving a JSON */
          const source = new Bokeh.AjaxDataSource({
            name: dataSource.source_name,
            data_url: dataSource.url,
            method: "GET",
            content_type: "",
            syncable: false,
            adapter: new Bokeh.CustomJS({code})
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
                width: Number(this.lineWidth) * dataSource.width
              }
            });
          bokehPlot.lines.unshift(line);
          const circle = bokehPlot.figure.circle(
            {field: "x"},
            {field: "y"},
            {
              ...attrs,
              ...{
                size: Number(this.symbolSize),
                visible: (dataSource.visible === undefined || dataSource.visible) &&
                  (dataSource.showSymbols === undefined || dataSource.showSymbols)
              }
            });
          const alphaAttrs = {};
          if (plot.alphaData !== undefined) {
            alphaAttrs.fill_alpha = {field: "alpha"};
          }
          circle.selection_glyph = new Bokeh.Circle({
            ...alphaAttrs,
            ...{
              fill_color: attrs.color,
              line_color: "black",
              line_width: 4
            }
          });
          circle.nonselection_glyph = new Bokeh.Circle({
            ...alphaAttrs,
            ...{
              fill_color: attrs.color,
              line_color: null
            }
          });
          bokehPlot.symbols.unshift(circle);

          let legend_label = this.legend_label(dataSource);

          /* Create legend */
          if (!legendLabels.has(legend_label)) {
            legendLabels.add(legend_label);
            const item = new Bokeh.LegendItem({
              label: legend_label,
              renderers: dataSource.showSymbols ? [circle,line]:[line],
              visible: dataSource.visible
            });
            bokehPlot.legendItems.unshift(item);
            dataSource.legend_item = item;  // for toggling visibility
          }
        }
      }

      /* Render figure(s) to HTML div */
      if (isNewPlot) {
        for (const [index, bokehPlot] of this.bokehPlots.entries()) {
          bokehPlot.legend = new Bokeh.Legend({items: bokehPlot.legendItems, visible: false});
          bokehPlot.figure.add_layout(bokehPlot.legend);
          Bokeh.Plotting.show(bokehPlot.figure, "#bokeh-plot-" + this.uuid + "-" + index);
        }
      }
    },
    refreshPlot() {
      for (const [dataSourceIdx, dataSource] of this.dataSources.entries()) {
        let visible = true;
        for (const categoryElem of this.categoryElements) {
          visible = visible && categoryElem.selection.includes(dataSource[categoryElem.key + '_index']);
        }

        if (dataSource.hasOwnProperty('legend_item')) {
          dataSource.legend_item.visible = visible;
          dataSource.legend_item.label = this.legend_label(dataSource);
        }

        for (const bokehPlot of this.bokehPlots) {
          const line = bokehPlot.lines[dataSourceIdx];
          line.visible = visible;
          line.glyph.line_width = Number(this.lineWidth) * dataSource.width;
          if (dataSource.is_topography_analysis) {
            line.glyph.line_alpha = Number(this.opacity);
          }

          const symbol = bokehPlot.symbols[dataSourceIdx];
          symbol.visible = visible && (dataSource.showSymbols === undefined || dataSource.showSymbols);
          symbol.glyph.size = Number(this.symbolSize);
          if (dataSource.is_topography_analysis) {
            symbol.glyph.line_alpha = Number(this.opacity);
            symbol.glyph.fill_alpha = Number(this.opacity);
          }
        }
      }
      for (const categoryElem of this.categoryElements) {
        categoryElem.isAllSelected = this.isAllSelected(categoryElem.elements, categoryElem.selection);
        categoryElem.isIndeterminate = this.isIndeterminate(categoryElem.elements, categoryElem.selection);
      }
    },
    isAllSelected(elements, selection) {
      return elements.length === selection.length;
    },
    isIndeterminate(elements, selection) {
      return selection.length !== elements.length && selection.length !== 0;
    },
    selectAll(category) {
      if (category.isAllSelected) {
        category.selection = [...Array(category.elements.length).keys()];
      } else {
        category.selection = [];
      }
    },
    onTap(obj, data) {
      /* Make sure only the selection for one topography is active
         and deselect all others */
      const name = data.source.name;
      const index = data.source.selected.indices[0];
      for (const bokehPlot of this.bokehPlots) {
        for (const source of bokehPlot.sources) {
          if (source.name === name) {
            source.selected.indices = [index];
          }
        }
      }

      /* Emit event */
      this.$emit("selected", obj, data);
    },
    download: function () {
      this.bokehPlots[0].save.do.emit();
    }
  }
});

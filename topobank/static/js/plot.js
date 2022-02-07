/*
 * Vue component that wraps a Bokeh plot and adds elements for controlling that plots appearance.
 * - Categories: Each dataset can be assigned multiple *categories*. Each category receives an accordion that allows to
 *   show/hide all datasets belonging to a specific value of this category. These categories are for example the names
 *   of a measurement and the data series (1D PSD, 2D PSD, etc.).
 */

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
          <div :id='"heading-"+uuid+"-"+category.name' class="card-header plot-controls-card-header">
            <h2 class="mb-0">
              <div class="accordion-header-control custom-checkbox">
                <input :id='"select-all-"+uuid+"-"+category.name'
                       class="custom-control-input"
                       type="checkbox"
                       value=""
                       v-model="category.isAllSelected"
                       v-on:change="selectAll(category)"
                       :indeterminate.prop="category.isIndeterminate">
                <label class="custom-control-label btn-block text-left"
                       :for='"select-all-"+uuid+"-"+category.name'>
                </label>
              </div>
              <button class="btn btn-link btn-block text-left accordion-button collapsed"
                      type="button"
                      data-toggle="collapse"
                      :data-target='"#collapse-"+uuid+"-"+category.name'
                      aria-expanded="false"
                      :aria-controls='"collapse-"+uuid+"-"+category.name'>
                {{ category.title }}
              </button>
            </h2>
          </div>
          <div :id='"collapse-"+uuid+"-"+category.name'
               class="collapse"
               :aria-labelledby='"heading-"+uuid+"-"+category.name'
               :data-parent='"#plot-controls-accordion-"+uuid'>
            <div :id='"card-subjects"+uuid' class="card-body plot-controls-card-body">
              <div v-for="(element, index) in category.elements" class="custom-control custom-checkbox">
                <input :id='"switch-"+uuid+"-"+category.name+"-"+index'
                       class="custom-control-input"
                       type="checkbox"
                       :value="index"
                       v-model="category.selection">
                <label class="custom-control-label"
                       :for='"switch-"+uuid+"-"+category.name+"-"+index'>
                  <span class="dot" v-if="element.color !== null" :style='"background-color: "+element.color'></span>
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
              <div class="form-group">
                <label :for='"plot-layout-"+uuid' hidden>Plot layout:</label>
                <select class="form-control"
                       :id='"plot-layout-"+uuid'
                       v-model="layout">
                  <option value="web">Optimize plot for web (plot scales with window size)</option>
                  <option value="print-single">Optimize plot for print (single-column layout)</option>
                  <option value="print-double">Optimize plot for print (two-column layout)</option>
                </select>
              </div>

<!-- Adjusting line width does not work
              <div class="form-group">
                <label :for='"line-width-slider-"+uuid'>Line width: <b>{{ lineWidth }}</b></label>
                <input :id='"line-width-slider-"+uuid'
                       type="range"
                       min="0.1"
                       max="2.0"
                       step="0.1"
                       class="form-control-range"
                       v-model="lineWidth">
              </div>
-->

              <div class="form-group">
                <label :for='"symbol-size-slider-"+uuid'>Symbol size: <b>{{ symbolSize }}</b></label>
                <input :id='"symbol-size-slider-"+uuid'
                       type="range"
                       min="1"
                       max="20"
                       step="1"
                       class="form-control-range"
                       v-model="symbolSize">
              </div>

              <div class="form-group">
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
      // List of dictionaries with keys:
      //   name: Name of dataset key that defines this category, i.e. if we have add a category with name "person",
      //         the code will expect a "person" key in the dataset, that specifies the value for this category.
      //   title: Title of this category.
      type: Array, default: []
    },
    plots: {
      // Define the plots to show. Each plot will display in its own tab if there is more than one.
      type: Array, default: [{title: "default", x: "x", y: "y"}]
    },
    dataSources: {
      // Defining data sources.
      // List of dictionaries with keys:
      //   [category-name]: Value of the specific category. For each category, there must be a key-value pair.
      //   url: URL to JSON that contains the data.
      //   color: Line and symbol color.
      //   show_symbols (optional): Show symbols for this data source?
      //   visible (optional): Initial visibility (can be triggered by user).
      type: Array, default: []
    },
    xAxisLabel: {
      type: String, default: "Please specify x-axis label"
    },
    yAxisLabel: {
      type: String, default: "Please specify y-axis label"
    },
    xAxisType: {
      type: String, default: "linear"
    },
    yAxisType: {
      type: String, default: "linear"
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
        return ["pan", "reset", "save", "wheel_zoom", "box_zoom", "hover"];
      }
    }
  },
  data: function () {
    return {
      uuid: null,  // Unique identifier that is embedded in the HTML ids
      layout: "web",
      opacity: 0.4,
      lineWidth: 1,
      symbolSize: 10,
      categoryElements: [],
      bokehPlots: [],  // Stores Bokeh figure, line and symbol objects
    };
  },
  created: function () {
    /* Create unique ID */
    this.uuid = crypto.randomUUID();

    /* For each category, create a list of unique entries */
    for (const [index, category] of this.categories.entries()) {
      let titles = new Set();
      let elements = [];
      let selection = [];

      for (const dataSource of this.dataSources) {

        if (!(category.name in dataSource)) {
          throw new Error("Key '" + category.name + "' not found in data source '" + dataSource.name + "'.");
        }

        const title = dataSource[category.name];
        if (!(titles.has(title))) {
          color = index == 0 ? dataSource.color : null;  // The first category defines the color
          titles.add(title);
          elements.push({title: title, color: color});
          // Default to showing a data source if it has no 'visible' attribute
          if (dataSource.visible === undefined || dataSource.visible) {
            selection.push(dataSource[category.name + '_index']);
          }
        }

      }

      this.categoryElements.push({
        name: category.name,
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
    dataSources: function (newVal, oldVal) {
      // We need to completely rebuild the plot if the dataSources change
      this.buildPlot();
    }
  },
  methods: {
    buildPlot() {
      /* Clear list of Bokeh plots */
      this.bokehPlots.length = 0;

      for (const plot of this.plots) {
        /* Callback for selection of data points */
        let tools = [...this.tools];  // Copy array (= would just be a reference)
        const code = "self.onTap(cb_obj, cb_data);";
        tools.push(new Bokeh.TapTool({
          behavior: "select",
          callback: new Bokeh.CustomJS({
            args: {self: this},
            code: code
          })
        }));

        /* Create and style figure */
        const bokehPlot = new Bokeh.Plotting.Figure({
          height: this.height,
          sizing_mode: this.sizingMode,
          x_axis_label: plot.xAxisLabel === undefined ? "x" : plot.xAxisLabel,
          y_axis_label: plot.yAxisLabel === undefined ? "y" : plot.yAxisLabel,
          x_axis_type: plot.xAxisType === undefined ? "linear" : plot.xAxisType,
          y_axis_type: plot.yAxisType === undefined ? "linear" : plot.yAxisType,
          tools: tools,
          output_backend: this.outputBackend
        });

        /* This should become a Bokeh theme (supported in BokehJS with 3.0 - but I cannot find the `use_theme` method) */
        bokehPlot.xaxis.axis_label_text_font_style = "normal";
        bokehPlot.yaxis.axis_label_text_font_style = "normal";
        bokehPlot.xaxis.major_label_text_font_size = "16px";
        bokehPlot.yaxis.major_label_text_font_size = "16px";
        bokehPlot.xaxis.axis_label_text_font_size = "16px";
        bokehPlot.yaxis.axis_label_text_font_size = "16px";

        this.bokehPlots.push({
          figure: bokehPlot,
          lines: [],
          symbols: []
        });
      }

      /* We iterate in reverse order because we want to the first element to appear on top of the plot */
      for (const dataSource of this.dataSources.reverse()) {
        for (const [index, plot] of this.plots.entries()) {
          /* Get scale factors */
          xscale_key = plot.x + "_scale";
          yscale_key = plot.y + "_scale";
          xscale = dataSource[xscale_key] === undefined ? 1 : dataSource[xscale_key];
          yscale = dataSource[yscale_key] === undefined ? 1 : dataSource[yscale_key];

          /* Get appropriate xy data and apply scale factors */
          const code = "return { x: cb_data.response." + plot.x + ".map(value => " + xscale + " * value), " + "y: cb_data.response." + plot.y + ".map(value => " + yscale + " * value) }";

          /* Data source: AJAX GET request to storage system retrieving a JSON */
          const source = new Bokeh.AjaxDataSource({
            name: dataSource.source_name,
            data_url: dataSource.url,
            method: "GET",
            content_type: "",
            syncable: false,
            adapter: new Bokeh.CustomJS({code})
          });

          /* Common attributes of lines and symbols */
          attrs = {
            source: source,
            visible: dataSource.visible,
            color: dataSource.color,
            alpha: dataSource.alpha
          }

          /* Create lines and symbols */
          const bokehPlot = this.bokehPlots[index];
          bokehPlot.lines.unshift(bokehPlot.figure.line(
            {field: "x"},
            {field: "y"},
            {
              ...attrs,
              ...{
                width: Number(this.lineWidth) * dataSource.width
              }
            }));
          bokehPlot.symbols.unshift(bokehPlot.figure.circle(
            {field: "x"},
            {field: "y"},
            {
              ...attrs,
              ...{
                size: Number(this.symbolSize),
                visible: (dataSource.visible === undefined || dataSource.visible) &&
                  (dataSource.show_symbols === undefined || dataSource.show_symbols)
              }
            }));
        }
      }

      /* Render figure(s) to HTML div */
      for (const [index, bokehPlot] of this.bokehPlots.entries()) {
        Bokeh.Plotting.show(bokehPlot.figure, "#bokeh-plot-" + this.uuid + "-" + index);
      }
    },
    refreshPlot() {
      for (const [index, dataSource] of this.dataSources.entries()) {
        let visible = true;
        for (const category of this.categoryElements) {
          visible = visible && category.selection.includes(dataSource[category.name + '_index']);
        }

        for (const bokehPlot of this.bokehPlots) {
          const line = bokehPlot.lines[index];
          line.visible = visible;
          line.glyph.line_width = Number(this.lineWidth) * dataSource.width;
          if (dataSource.is_topography_analysis) {
            line.glyph.line_alpha = Number(this.opacity);
          }

          const symbols = bokehPlot.symbols[index];
          symbols.visible = visible && (dataSource.show_symbols === undefined || dataSource.show_symbols);
          symbols.glyph.size = Number(this.symbolSize);
          if (dataSource.is_topography_analysis) {
            symbols.glyph.line_alpha = Number(this.opacity);
          }
        }
      }
      for (const category of this.categoryElements) {
        category.isAllSelected = this.isAllSelected(category.elements, category.selection);
        category.isIndeterminate = this.isIndeterminate(category.elements, category.selection);
      }
    },
    isAllSelected(elements, selection) {
      return elements.length == selection.length;
    },
    isIndeterminate(elements, selection) {
      return selection.length != elements.length && selection.length != 0;
    },
    selectAll(category) {
      console.log(category);
      if (category.isAllSelected) {
        category.selection = [...Array(category.elements.length).keys()];
      } else {
        category.selection = [];
      }
    },
    onTap(obj, data) {
      /**
       * Make sure only the selection for one topography is active
       * and deselect all others
       */
      /*
      for (let i = 0; i < sources.length; i++) {
        var selection = []; // default: unselect all points
        var s = sources[i];

        if (s == data.source) {
          // console.log("Skipping source "+s+" ...");
          continue; // we do not modify the source for the clicked point, should be okay as bokeh does it
        }

        if (name == s.name) {
          selection = [index]; // if name of source is same as clicked point, select point equivalent point there
        }

        // console.log("Selection for source "+s+": "+selection);
        sources[i].selected.indices = selection;
      }
      */

      // Emit event
      this.$emit("tapped", obj, data);
    }
  }
});

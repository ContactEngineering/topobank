Vue.component("bokeh-plot", {
  template: `
    <div>
      <div :id='"bokeh-plot-"+uniquePrefix' ref="bokehPlot"></div>
      <div :id='"plot-controls-accordion-"+uniquePrefix' class="accordion plot-controls-accordion">
        <div v-for="category in categoryElements" class="card">
          <div :id='"heading-"+uniquePrefix+"-"+category.name' class="card-header plot-controls-card-header">
            <h2 class="mb-0">
              <div class="accordion-header-control custom-checkbox">
                <input :id='"select-all-"+uniquePrefix+"-"+category.name'
                       class="custom-control-input"
                       type="checkbox"
                       value=""
                       v-model="category.isAllSelected"
                       v-on:change="selectAll(category)"
                       :indeterminate.prop="category.isIndeterminate">
                <label class="custom-control-label btn-block text-left"
                       :for='"select-all-"+uniquePrefix+"-"+category.name'>
                </label>
              </div>
              <button class="btn btn-link btn-block text-left accordion-button collapsed"
                      type="button"
                      data-toggle="collapse"
                      :data-target='"#collapse-"+uniquePrefix+"-"+category.name'
                      aria-expanded="false"
                      :aria-controls='"collapse-"+uniquePrefix+"-"+category.name'>
                {{ category.title }}
              </button>
            </h2>
          </div>
          <div :id='"collapse-"+uniquePrefix+"-"+category.name'
               class="collapse"
               :aria-labelledby='"heading-"+uniquePrefix+"-"+category.name'
               :data-parent='"#plot-controls-accordion-"+uniquePrefix'>
            <div :id='"card-subjects"+uniquePrefix' class="card-body plot-controls-card-body">
              <div v-for="(element, index) in category.elements" class="custom-control custom-checkbox">
                <input :id='"switch-"+uniquePrefix+"-"+category.name+"-"+index'
                       class="custom-control-input"
                       type="checkbox"
                       :value="index"
                       v-model="category.selection">
                <label class="custom-control-label"
                       :for='"switch-"+uniquePrefix+"-"+category.name+"-"+index'>
                  <span class="dot" v-if="element.color !== null" :style='"background-color: "+element.color'></span>
                    {{ element.title }}
                </label>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div :id='"heading-plot-options-"+uniquePrefix' class="card-header plot-controls-card-header">
            <h2 class="mb-0">
              <button class="btn btn-link btn-block text-left accordion-button collapsed"
                      type="button"
                      data-toggle="collapse"
                      :data-target='"#collapse-plot-options-"+uniquePrefix'
                      aria-expanded="false"
                      :aria-controls='"collapse-plot-options-"+uniquePrefix'>
                Plot options
              </button>
            </h2>
          </div>
          <div :id='"collapse-plot-options-"+uniquePrefix'
               class="collapse"
               :aria-labelledby='"heading-plot-options-"+uniquePrefix'
               :data-parent='"#plot-controls-accordion-"+uniquePrefix'>


            <div class="card-body plot-controls-card-body">
              <div class="form-group">
                <label :for='"plot-layout-"+uniquePrefix' hidden>Plot layout:</label>
                <select class="form-control"
                       :id='"plot-layout-"+uniquePrefix'
                       v-model="layout">
                  <option value="web">Optimize plot for web (plot scales with window size)</option>
                  <option value="print-single">Optimize plot for print (single-column layout)</option>
                  <option value="print-double">Optimize plot for print (two-column layout)</option>
                </select>
              </div>

<!-- Adjusting line width does not work
              <div class="form-group">
                <label :for='"line-width-slider-"+uniquePrefix'>Line width: <b>{{ lineWidth }}</b></label>
                <input :id='"line-width-slider-"+uniquePrefix'
                       type="range"
                       min="0.1"
                       max="2.0"
                       step="0.1"
                       class="form-control-range"
                       v-model="lineWidth">
              </div>
-->

              <div class="form-group">
                <label :for='"symbol-size-slider-"+uniquePrefix'>Symbol size: <b>{{ symbolSize }}</b></label>
                <input :id='"symbol-size-slider-"+uniquePrefix'
                       type="range"
                       min="1"
                       max="20"
                       step="1"
                       class="form-control-range"
                       v-model="symbolSize">
              </div>

              <div class="form-group">
                <label :for='"opacity-slider-"+uniquePrefix'>Opacity of lines/symbols (measurements only): <b>{{ opacity }}</b></label>
                <input :id='"opacity-slider-"+uniquePrefix'
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
    uniquePrefix: String,  // This makes ids here unique - there should be a more elegant way to achieve this
    dataSources: Array,
    categories: Array,
    xAxisLabel: String,
    yAxisLabel: String,
    xAxisType: String,
    yAxisType: String,
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
      layout: "web", opacity: 0.4, lineWidth: 1, symbolSize: 10, categoryElements: []
    };
  },
  created: function () {
    /* For each category, create a list of unique entries */
    for (const [index, category] of this.categories.entries()) {
      let titles = new Set();
      let elements = [];
      let selection = [];

      for (const dataSource of this.dataSources) {

        if (!(category.name in dataSource)) {
          throw new Error("Key '" + category.name + "' not found in data source '" + dataSource.name + "'.");
        }

        title = dataSource[category.name];
        if (!(titles.has(title))) {
          color = index == 0 ? dataSource.color : null;  // The first category defines the color
          titles.add(title);
          elements.push({title: title, color: color});
          if (dataSource.visible) {
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
          this.plot.sizing_mode = "scale_width";
          this.plot.width = null;
          this.plot.height = 300;
          this.symbolSize = 10;
          break;
        case 'print-single':
          this.plot.sizing_mode = "fixed";
          this.plot.width = 600;
          this.plot.height = 300;
          this.symbolSize = 5;
          break;
        case 'print-double':
          this.plot.sizing_mode = "fixed";
          this.plot.width = 400;
          this.plot.height = 250;
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
    }
  }, methods: {
    buildPlot() {
      for (const child of this.$refs.bokehPlot.children) {
        this.$refs.bokehPlot.removeChild(child);
      }

      /* Create and style figure */
      const plot = new Bokeh.Plotting.Figure({
        height: this.height,
        sizing_mode: this.sizingMode,
        x_axis_label: this.xAxisLabel,
        y_axis_label: this.yAxisLabel,
        x_axis_type: this.xAxisType,
        y_axis_type: this.yAxisType,
        tools: this.tools,
        output_backend: this.outputBackend
      });

      /* This should become a Bokeh theme
         (supported in BokehJS with 3.0 - but I cannot find the `use_theme` method) */
      plot.xaxis.axis_label_text_font_style = "normal";
      plot.yaxis.axis_label_text_font_style = "normal";
      plot.xaxis.major_label_text_font_size = "16px";
      plot.yaxis.major_label_text_font_size = "16px";
      plot.xaxis.axis_label_text_font_size = "16px";
      plot.yaxis.axis_label_text_font_size = "16px";

      /* We iterate in reverse order because we want to the first element to appear on top of the plot */
      for (const dataSource of this.dataSources.reverse()) {
        /* Rescale all data to identical units */
        const code = "return { x: cb_data.response.x.map(value => " + dataSource.xscale + " * value), " + "y: cb_data.response.y.map(value => " + dataSource.yscale + " * value) };";

        /* Data source: AJAX GET request to storage system retrieving a JSON */
        const source = new Bokeh.AjaxDataSource({
          data_url: dataSource.url,
          method: "GET",
          content_type: "",
          syncable: false,
          adapter: new Bokeh.CustomJS({code})
        });

        /* Common attributes of lines and symbols */
        attrs = {
          source: source, visible: dataSource.visible, color: dataSource.color, alpha: dataSource.alpha
        }

        /* Create lines and symbols */
        dataSource.line = plot.line({field: "x"}, {field: "y"}, {...attrs, ...{width: Number(this.lineWidth) * dataSource.width}});
        dataSource.symbols = plot.circle({field: "x"}, {field: "y"}, {
          ...attrs, ...{
            size: Number(this.symbolSize),
            visible: dataSource.visible && dataSource.show_symbols
          }
        });
      }

      /* Render figure to HTML div */
      this.element = Bokeh.Plotting.show(plot, "#bokeh-plot-" + this.uniquePrefix);
      this.plot = plot;
    },
    refreshPlot() {
      for (const dataSource of this.dataSources) {
        visible = true;
        for (const category of this.categoryElements) {
          visible = visible && category.selection.includes(dataSource[category.name + '_index']);
        }
        dataSource.line.visible = visible;
        dataSource.symbols.visible = visible && dataSource.show_symbols;
        dataSource.line.glyph.line_width = Number(this.lineWidth) * dataSource.width;
        dataSource.symbols.glyph.size = Number(this.symbolSize);
        if (dataSource.is_topography_analysis) {
          dataSource.line.glyph.line_alpha = Number(this.opacity);
          dataSource.symbols.glyph.line_alpha = Number(this.opacity);
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
  }
});

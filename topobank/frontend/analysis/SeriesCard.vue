<script>

import BokehPlot from '../components/BokehPlot.vue';

export default {
  name: 'plot-card',
  components: {
    BokehPlot
  },
  props: {
    apiUrl: String,
    csrfToken: String,
    downloadXlsUrl: String,
    downloadTxtUrl: String,
    functionId: Number,
    functionName: String,
    subjects: Object
  },
  data() {
    return {
      analysesAvailable: false,
      categories: undefined,
      dataSources: undefined,
      hasWarnings: false,
      outputBackend: undefined,
      plots: undefined,
      title: this.functionName
    }
  },
  mounted() {
    /* Fetch JSON describing the card */
    fetch(this.apiUrl, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-CSRFToken': this.csrfToken
      },
      body: JSON.stringify({
        function_id: this.functionId,
        subjects: this.subjects
      })
    })
        .then(response => response.json())
        .then(data => {
          console.log(data);
          this.title = data.title;
          this.plots = [{
            title:"default",
            xAxisLabel:data.x_axis_label,
            yAxisLabel:data.y_axis_label,
            xAxisType:data.x_axis_type,
            yAxisType:data.y_axis_type
          }];
          this.dataSources = data.data_sources;
          this.categories = data.categories;
          this.outputBackend = data.outputBackend;
          this.analysesAvailable = true;
        });
  }
}
</script>

<template>
  <div class="card search-result-card">
    <div class="card-header">
      <!--
      <div v-if="analyses_available" class="btn-group btn-group-sm float-right">
      -->
      <div class="btn-group btn-group-sm float-right">
        <!--
        <button v-if="!analyses_unready" class="btn btn-primary btn-sm float-right" href="#" data-toggle="modal"
                data-target="#statusesModal">{% fa5_icon 'tasks' %} Tasks
        </button>
        -->
        <button class="btn btn-default btn-sm float-right" href="#" data-toggle="modal"
                data-target="#statusesModal">Tasks
        </button>
        <div class="btn-group btn-group-sm float-right dropdown">
          <a href="{% url 'analysis:function-detail' function.pk %}" class="btn btn-default float-right open-btn">
            Open
          </a>
          <button type="button" class="btn btn-default" data-toggle="dropdown"
                  aria-haspopup="true" aria-expanded="false">
            <i class="fa fa-chevron-down"></i>
          </button>
          <div class="dropdown-menu dropdown-menu-right">
            <!--
            {% if analyses_success %}
            <a class="dropdown-item"
               href="{% url 'analysis:download' analyses_success|analyses_results_ids_list_str 'series' 'txt' %}">Download
              TXT</a>
            <a class="dropdown-item"
               href="{% url 'analysis:download' analyses_success|analyses_results_ids_list_str 'series' 'xlsx' %}">Download
              XLSX</a>
            <a class="dropdown-item" v-on:click="$refs.plot.download()">Download SVG</a>
            <div class="dropdown-divider"></div>
            {% endif %}
            -->
            <a class="dropdown-item" href="#" data-toggle="modal"
               data-target="#doisModal">References</a>
          </div>
        </div>
      </div>
      <h5>{{ title }}</h5>
    </div>
    <div class="card-body">
      <ul v-if="has_warnings" class="nav nav-tabs">
        <li class="nav-item" style="list-style-type: none;">
          <a class="nav-link active" data-toggle="tab" href="#plot-tab">Plot</a>
        </li>
        <li class="nav-item" style="list-style-type: none;">
          <a class="nav-link" data-toggle="tab" href="#warnings-tab">Warnings</a>
        </li>
      </ul>

      <div v-if="!analysesAvailable" class="tab-content">
        <span class="spinner"></span>
        <div>Please wait...</div>
      </div>

      <div v-if="analysesAvailable" class="tab-content">
        <div class="tab-pane show active" id="plot-tab" role="tabpanel" aria-label="Tab showing a plot">
          <!-- {% include 'analysis/analyses_alerts.html' %} -->
          <bokeh-plot
              :plots="this.plots"
              :categories="this.categories"
              :data-sources="this.dataSources"
              :output-backend="this.outputBackend"
              ref="plot">
          </bokeh-plot>
        </div>
        <!--
        {% include 'analysis/analyses_warnings_tab_pane.html' %}
        -->
      </div>
    </div>
  </div>
</template>

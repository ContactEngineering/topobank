<script>

import BokehPlot from '../components/BokehPlot.vue';

export default {
  name: 'plot-card',
  components: {
    BokehPlot
  },
  props: {
    functionName: String,
    subjectIds: Object,
    downloadTxtUrl: String,
    downloadXlsUrl: String
  },
  data() {
    return {
      title: 'Test',
      analyses_available: false,
      has_warnings: false
    }
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
                data-target="#statusesModal-{{ card_id }}">{% fa5_icon 'tasks' %} Tasks
        </button>
        -->
        <button class="btn btn-default btn-sm float-right" href="#" data-toggle="modal"
                data-target="#statusesModal-{{ card_id }}">Tasks
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
               data-target="#doisModal-{{ card_id }}">References</a>
          </div>
        </div>
      </div>
      <h5>{{ functionName }}</h5>
    </div>
    <div class="card-body">
      <ul v-if="has_warnings" class="nav nav-tabs">
        <li class="nav-item" style="list-style-type: none;">
          <a class="nav-link active" data-toggle="tab" href="#plot-tab-{{ card_id }}">Plot</a>
        </li>
        <li class="nav-item" style="list-style-type: none;">
          <a class="nav-link" data-toggle="tab" href="#warnings-tab-{{ card_id }}">Warnings</a>
        </li>
      </ul>

      <div class="tab-content">
        <div class="tab-pane show active" id="plot-tab-{{ card_id }}" role="tabpanel" aria-label="Tab showing a plot">
          {{ subjectIds }}
          <!-- {% include 'analysis/analyses_alerts.html' %} -->
          <!--
          <bokeh-plot
              :plots='[{title:"default", xAxisLabel:"{{ x_axis_label }}", yAxisLabel:"{{ y_axis_label }}", xAxisType:"{{ x_axis_type }}", yAxisType:"{{ y_axis_type }}"}]'
              :categories='{{ categories|safe }}'
              :data-sources='{{ data_sources|safe }}'
              output-backend="{{ output_backend }}"
              ref="plot">
          </bokeh-plot>
          -->
        </div>
        <!--
        {% include 'analysis/analyses_warnings_tab_pane.html' %}
        -->
      </div>
    </div>
  </div>
</template>

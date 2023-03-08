<script>

import {v4 as uuid4} from 'uuid';

import BokehPlot from '../components/BokehPlot.vue';
import BibliographyModal from './BibliographyModal.vue';
import TaskButton from './TaskButton.vue';

export default {
  name: 'series-card',
  components: {
    BibliographyModal,
    BokehPlot,
    TaskButton
  },
  props: {
    apiUrl: String,
    csrfToken: String,
    functionId: Number,
    functionName: String,
    subjects: Object,
    txtDownloadUrl: String,
    uid: {
      type: String,
      default() {
        return uuid4();
      }
    },
    xlsxDownloadUrl: String
  },
  data() {
    return {
      analyses: [],
      analysesAvailable: false,
      categories: undefined,
      dataSources: undefined,
      dois: [],
      hasWarnings: false,
      outputBackend: undefined,
      plots: undefined,
      title: this.functionName
    }
  },
  mounted() {
    /* Fetch JSON describing the card */
    var _this = this;
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
          _this.analyses = data.analyses;
          _this.title = data.plotConfiguration.title;
          _this.plots = [{
            title: "default",
            xAxisLabel: data.plotConfiguration.xAxisLabel,
            yAxisLabel: data.plotConfiguration.yAxisLabel,
            xAxisType: data.plotConfiguration.xAxisType,
            yAxisType: data.plotConfiguration.yAxisType
          }];
          _this.dataSources = data.plotConfiguration.dataSources;
          _this.categories = data.plotConfiguration.categories;
          _this.outputBackend = data.plotConfiguration.outputBackend;
          _this.dois = data.dois;
          _this.analysesAvailable = true;
        });
  }
};
</script>

<template>
  <div class="card search-result-card">
    <div class="card-header">
      <div class="btn-group btn-group-sm float-right">
        <task-button :analyses="analyses"
                     :csrf-token="csrfToken">
        </task-button>
        <div class="btn-group btn-group-sm float-right pl-1">
          <a href="{% url 'analysis:function-detail' function.pk %}" class="btn btn-default float-right">
            <i class="fa fa-redo"></i>
          </a>
        </div>
        <div class="btn-group btn-group-sm float-right">
          <a href="{% url 'analysis:function-detail' function.pk %}" class="btn btn-default float-right">
            <i class="fa fa-expand"></i>
          </a>
        </div>
      </div>
      <a class="text-dark" href="#" data-toggle="collapse" :data-target="`#sidebar-${uid}`">
        <h5><i class="fa fa-bars"></i> {{ title }}</h5>
      </a>
    </div>
    <div class="card-body">
      <div v-if="!analysesAvailable" class="tab-content">
        <span class="spinner"></span>
        <div>Please wait...</div>
      </div>

      <div v-if="analysesAvailable" class="tab-content">
        <div class="tab-pane show active" role="tabpanel" aria-label="Tab showing a plot">
          <!-- {% include 'analysis/analyses_alerts.html' %} -->
          <bokeh-plot
              :plots="this.plots"
              :categories="this.categories"
              :data-sources="this.dataSources"
              :output-backend="this.outputBackend"
              ref="plot">
          </bokeh-plot>
        </div>
      </div>
    </div>
    <div :id="`sidebar-${uid}`" class="col-1 col-sm-6 p-0 collapse sidebar position-absolute h-100">
      <!-- card-header sets the margins identical to the card so the title appears at the same position -->
      <nav class="card-header navbar navbar-toggleable-xl bg-light flex-column align-items-start h-100">
        <ul class="flex-column navbar-nav">
          <a class="text-dark" href="#" data-toggle="collapse" :data-target="`#sidebar-${uid}`">
            <h5><i class="fa fa-bars"></i> {{ title }}</h5>
          </a>
          <li class="nav-item">
            Download
            <a :href="txtDownloadUrl">
              TXT
            </a>
            <a :href="xlsxDownloadUrl">
              XLSX
            </a>
            <a v-on:click="$refs.plot.download()">
              SVG
            </a>
          </li>
          <li class="nav-item">
            <a href="#" data-toggle="modal" :data-target="`#bibliography-modal-${uid}`">
              Bibliography
            </a>
          </li>
        </ul>
      </nav>
    </div>
  </div>
  <bibliography-modal
      :id="`bibliography-modal-${uid}`"
      :dois="dois">
  </bibliography-modal>
</template>

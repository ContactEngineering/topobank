<script>

import {v4 as uuid4} from 'uuid';

import BokehPlot from '../components/BokehPlot.vue';
import BibliographyModal from './BibliographyModal.vue';
import TasksButton from './TasksButton.vue';

export default {
  name: 'series-card',
  components: {
    BibliographyModal,
    BokehPlot,
    TasksButton
  },
  props: {
    apiUrl: String,
    csrfToken: String,
    detailUrl: String,
    enlarged: {
      type: Boolean,
      default: true
    },
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
      _nbFailed: 0,
      _nbRunningOrPending: 0,
      _nbSuccess: 0,
      outputBackend: "svg",
      plots: undefined,
      title: this.functionName
    }
  },
  mounted() {
    this.updateCard();
  },
  computed: {
    analysisIds() {
      return this.analyses.map(a => a.id).join();
    }
  },
  methods: {
    updateCard() {
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
            this.analyses = data.analyses;
            this.title = data.plotConfiguration.title;
            this.plots = [{
              title: "default",
              xAxisLabel: data.plotConfiguration.xAxisLabel,
              yAxisLabel: data.plotConfiguration.yAxisLabel,
              xAxisType: data.plotConfiguration.xAxisType,
              yAxisType: data.plotConfiguration.yAxisType
            }];
            this.dataSources = data.plotConfiguration.dataSources;
            this.categories = data.plotConfiguration.categories;
            this.outputBackend = data.plotConfiguration.outputBackend;
            this.dois = data.dois;
            this.analysesAvailable = true;
          });
    },
    taskStateChanged(nbRunningOrPending, nbSuccess, nbFailed) {
      if (nbRunningOrPending == 0 && this._nbRunningOrPending > 0) {
          // All tasks finished, reload card
          this.updateCard();
      }
      this._nbRunningOrPending = nbRunningOrPending;
      this._nbSuccess = nbSuccess;
      this._nbFailed = nbFailed;
    }
  }
};
</script>

<template>
  <div class="card search-result-card">
    <div class="card-header">
      <div class="btn-group btn-group-sm float-right">
        <tasks-button :analyses="analyses"
                      :csrf-token="csrfToken"
                      @task-state-changed="taskStateChanged">
        </tasks-button>
        <button @click="updateCard" class="btn btn-default float-right ml-1">
          <i class="fa fa-redo"></i>
        </button>
        <div v-if="!enlarged" class="btn-group btn-group-sm float-right">
          <a :href="detailUrl" class="btn btn-default float-right">
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
          <bokeh-plot
              :plots="plots"
              :categories="categories"
              :data-sources="dataSources"
              :output-backend="outputBackend"
              ref="plot">
          </bokeh-plot>
        </div>
      </div>
    </div>
    <div :id="`sidebar-${uid}`" class="collapse position-absolute h-100">
      <!-- card-header sets the margins identical to the card so the title appears at the same position -->
      <nav class="card-header navbar navbar-toggleable-xl bg-light flex-column align-items-start h-100">
        <ul class="flex-column navbar-nav">
          <a class="text-dark" href="#" data-toggle="collapse" :data-target="`#sidebar-${uid}`">
            <h5><i class="fa fa-bars"></i> {{ title }}</h5>
          </a>
          <li class="nav-item mb-1 mt-1">
            Download
            <div class="btn-group ml-1" role="group" aria-label="Download formats">
              <a :href="`/analysis/download/${analysisIds}/txt`" class="btn btn-default">
                TXT
              </a>
              <a :href="`/analysis/download/${analysisIds}/xlsx`" class="btn btn-default">
                XLSX
              </a>
              <a v-on:click="$refs.plot.download()" class="btn btn-default">
                SVG
              </a>
            </div>
          </li>
          <li class="nav-item mb-1 mt-1">
            <a href="#" data-toggle="modal" :data-target="`#bibliography-modal-${uid}`" class="btn btn-default  w-100">
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

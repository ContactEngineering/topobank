<script>

import {v4 as uuid4} from 'uuid';

import BokehPlot from '../components/BokehPlot.vue';
import BibliographyModal from './BibliographyModal.vue';

export default {
  name: 'plot-card',
  components: {
    BibliographyModal,
    BokehPlot
  },
  props: {
    apiUrl: String,
    csrfToken: String,
    functionId: Number,
    functionName: String,
    subjects: Object,
    txtDownloadUrl: String,
    uid: {
      type: Number,
      default() {
        return uuid4();
      }
    },
    xlsxDownloadUrl: String
  },
  data() {
    return {
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
            title: "default",
            xAxisLabel: data.xAxisLabel,
            yAxisLabel: data.yAxisLabel,
            xAxisType: data.xAxisType,
            yAxisType: data.yAxisType
          }];
          this.dataSources = data.dataSources;
          this.categories = data.categories;
          this.outputBackend = data.outputBackend;
          this.dois = data.dois;
          this.analysesAvailable = true;
        });
  }
}
</script>

<template>
  <div class="card search-result-card">
    <div class="card-header">
      <div class="btn-group btn-group-sm float-right">
        <button class="btn btn-default btn-sm float-right" href="#" data-toggle="modal"
                data-target="#statusesModal">
          Tasks
        </button>
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
          <a href="#" data-toggle="collapse" :data-target="`#sidebar-${uid}`">
            <h5 class="text-black"><i class="fa fa-bars"></i> {{ title }}</h5>
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
            <a href="#" data-toggle="modal" :data-target="`#bibliography-model-${uid}`">
              Bibliography
            </a>
          </li>
        </ul>
      </nav>
    </div>
  </div>
  <bibliography-modal :id="`bibliography-model-${uid}`" :dois="dois"></bibliography-modal>
</template>

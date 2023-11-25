<script setup>

import axios from "axios";
import {v4 as uuid4} from 'uuid';
import {computed, onMounted, ref} from "vue";

import {BSpinner} from 'bootstrap-vue-next';

import BokehPlot from '../components/BokehPlot.vue';
import BibliographyModal from './BibliographyModal.vue';
import CardExpandButton from './CardExpandButton.vue';
import TasksButton from './TasksButton.vue';

const props = defineProps({
    apiUrl: {
        type: String,
        default: '/analysis/api/card/series'
    },
    detailUrl: {
        type: String,
        default: '/analysis/html/detail/'
    },
    enlarged: {
        type: Boolean,
        default: true
    },
    functionId: Number,
    functionName: String,
    subjects: String,
    uid: {
        type: String,
        default() {
            return uuid4();
        }
    }
});

// Information about analyses that this card display
const _title = ref(props.functionName);
const _analyses = ref(null);

// Plot configuration
const _categories = ref(null);
const _dataSources = ref(null);
const _outputBackend = ref("svg");
const _plots = ref(null);
const _showSymbols = ref(true);

// GUI logic
const _sidebarVisible = ref(false);

// Auxiliary information
const _dois = ref([]);
const _messages = ref([]);

// Current task status
let _nbRunningOrPending = 0;


onMounted(() => {
    updateCard();
});


const analysisIds = computed(() => {
    if (_analyses == null) {
        return [];
    } else {
        return _analyses.value.map(a => a.id).join();
    }
});

function updateCard() {
    /* Fetch JSON describing the card */
    axios.get(`${props.apiUrl}/${props.functionId}?subjects=${props.subjects}`)
        .then(response => {
            _analyses.value = response.data.analyses;
            _title.value = response.data.plotConfiguration.title;
            _plots.value = [{
                title: "default",
                xAxisLabel: response.data.plotConfiguration.xAxisLabel,
                yAxisLabel: response.data.plotConfiguration.yAxisLabel,
                xAxisType: response.data.plotConfiguration.xAxisType,
                yAxisType: response.data.plotConfiguration.yAxisType
            }];
            _dataSources.value = response.data.plotConfiguration.dataSources;
            _categories.value = response.data.plotConfiguration.categories;
            _outputBackend.value = response.data.plotConfiguration.outputBackend;
            _showSymbols.value =  response.data.plotConfiguration.showSymbols;
            _dois.value = response.data.dois;
            _messages.value = response.data.messages;
        });
}

function taskStateChanged(nbRunningOrPending, nbSuccess, nbFailed) {
    if (nbRunningOrPending === 0 && _nbRunningOrPending > 0) {
        // All tasks finished, reload card
        updateCard();
    }
    _nbRunningOrPending = nbRunningOrPending;
}

</script>

<template>
    <div class="card search-result-card">
        <div class="card-header">
            <div class="btn-group btn-group-sm float-end">
                <tasks-button v-if="_analyses !== null && _analyses.length > 0"
                              :analyses="_analyses"
                              @task-state-changed="taskStateChanged">
                </tasks-button>
                <button v-if="_analyses !== null && _analyses.length > 0"
                        @click="updateCard"
                        class="btn btn-default float-end ms-1">
                    <i class="fa fa-redo"></i>
                </button>
                <card-expand-button v-if="!enlarged"
                                    :detail-url="detailUrl"
                                    :function-id="functionId"
                                    :subjects="subjects"
                                    class="btn-group btn-group-sm float-end">
                </card-expand-button>
            </div>
            <h5 v-if="_analyses === null"
                class="text-dark">
                {{ _title }}
            </h5>
            <a v-if="_analyses !== null && _analyses.length > 0"
               class="text-dark text-decoration-none"
               href="#"
               @click="_sidebarVisible=true">
                <h5><i class="fa fa-bars"></i> {{ _title }}</h5>
            </a>
        </div>
        <div class="card-body">
            <div v-if="_analyses == null || _dataSources == null"
                 class="tab-content">
                <b-spinner type="grow" small/>
                Collecting analysis status, please wait...
            </div>
            <div v-if="_analyses != null && _dataSources != null && _dataSources.length === 0"
                 class="tab-content">
                <b-spinner small/>
                Analysis tasks are scheduled or running, please wait...
            </div>

            <div v-if="_analyses !== null && _analyses.length === 0" class="tab-content">
                This analysis reported no results for the selected datasets.
            </div>

            <div v-if="_analyses !== null && _dataSources !== null && _analyses.length > 0 && _dataSources.length > 0"
                 class="tab-content">
                <div class="tab-pane show active" role="tabpanel" aria-label="Tab showing a plot">
                    <div :class="['alert', message.alertClass]" v-for="message in _messages">
                        {{ message.message }}
                    </div>
                    <bokeh-plot
                        :plots="_plots"
                        :categories="_categories"
                        :data-sources="_dataSources"
                        :output-backend="_outputBackend"
                        :show-symbols="_showSymbols"
                        :functionTitle="_title"
                        ref="plot">
                    </bokeh-plot>
                </div>
            </div>
        </div>
        <div v-if="_sidebarVisible"
             class="position-absolute h-100">
            <!-- card-header sets the margins identical to the card so the title appears at the same position -->
            <nav class="card-header navbar navbar-toggleable-xl bg-light flex-column align-items-start h-100">
                <ul class="flex-column navbar-nav">
                    <a class="text-dark"
                       href="#"
                       @click="_sidebarVisible=false">
                        <h5><i class="fa fa-bars"></i> {{ _title }}</h5>
                    </a>
                    <li class="nav-item mb-1 mt-1">
                        Download
                        <div class="btn-group ms-1" role="group" aria-label="Download formats">
                            <a :href="`/analysis/download/${analysisIds}/txt`"
                               class="btn btn-default"
                               @click="_sidebarVisible=false">
                                TXT
                            </a>
                            <a :href="`/analysis/download/${analysisIds}/csv`"
                               class="btn btn-default"
                               @click="_sidebarVisible=false">
                                CSV
                            </a>
                            <a :href="`/analysis/download/${analysisIds}/xlsx`"
                               class="btn btn-default"
                               @click="_sidebarVisible=false">
                                XLSX
                            </a>
                            <a @click="_sidebarVisible=false; $refs.plot.download()"
                               class="btn btn-default">
                                SVG
                            </a>
                        </div>
                    </li>
                    <li class="nav-item mb-1 mt-1">
                        <a href="#"
                           data-toggle="modal"
                           :data-target="`#bibliography-modal-${uid}`"
                           class="btn btn-default w-100"
                           @click="_sidebarVisible=false">
                            Bibliography
                        </a>
                    </li>
                </ul>
            </nav>
        </div>
    </div>
    <bibliography-modal
        :id="`bibliography-modal-${uid}`"
        :dois="_dois">
    </bibliography-modal>
</template>

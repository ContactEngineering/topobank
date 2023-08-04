<script>

import {v4 as uuid4} from 'uuid';

import BokehPlot from '../components/BokehPlot.vue';
import BibliographyModal from './BibliographyModal.vue';
import CardExpandButton from './CardExpandButton.vue';
import TasksButton from './TasksButton.vue';

export default {
    name: 'series-card',
    components: {
        BibliographyModal,
        BokehPlot,
        CardExpandButton,
        TasksButton
    },
    props: {
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
    },
    inject: ['csrfToken'],
    data() {
        return {
            _analyses: null,
            _categories: undefined,
            _dataSources: undefined,
            _dois: [],
            _messages: [],
            _nbFailed: 0,
            _nbRunningOrPending: 0,
            _nbSuccess: 0,
            _outputBackend: "svg",
            _plots: undefined,
            _sidebarVisible: false,
            _title: this.functionName
        }
    },
    mounted() {
        this.updateCard();
    },
    watch: {
        functionId(newValue, oldValue) {
            // Function id may update when the user selects or deselects an analysis to show.
            // The subject do not update in that case.
            this.updateCard();
        }
    },
    computed: {
        analysisIds() {
            return this._analyses.map(a => a.id).join();
        }
    },
    methods: {
        updateCard() {
            /* Fetch JSON describing the card */
            fetch(`${this.apiUrl}/${this.functionId}?subjects=${this.subjects}`, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                    'X-CSRFToken': this.csrfToken
                }
            })
                .then(response => response.json())
                .then(data => {
                    this._analyses = data.analyses;
                    this._title = data.plotConfiguration.title;
                    this._plots = [{
                        title: "default",
                        xAxisLabel: data.plotConfiguration.xAxisLabel,
                        yAxisLabel: data.plotConfiguration.yAxisLabel,
                        xAxisType: data.plotConfiguration.xAxisType,
                        yAxisType: data.plotConfiguration.yAxisType
                    }];
                    this._dataSources = data.plotConfiguration.dataSources;
                    this._categories = data.plotConfiguration.categories;
                    this._outputBackend = data.plotConfiguration.outputBackend;
                    this._dois = data.dois;
                    this._messages = data.messages;
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
                <tasks-button v-if="_analyses !== null && _analyses.length > 0"
                              :analyses="_analyses"
                              :csrf-token="csrfToken"
                              @task-state-changed="taskStateChanged">
                </tasks-button>
                <button v-if="_analyses !== null && _analyses.length > 0"
                        @click="updateCard"
                        class="btn btn-default float-right ml-1">
                    <i class="fa fa-redo"></i>
                </button>
                <card-expand-button v-if="!enlarged"
                                    :detail-url="detailUrl"
                                    :function-id="functionId"
                                    :subjects="subjects"
                                    class="btn-group btn-group-sm float-right">
                </card-expand-button>
            </div>
            <h5 v-if="_analyses === null"
                class="text-dark">
                {{ _title }}
            </h5>
            <a v-if="_analyses !== null && _analyses.length > 0"
               class="text-dark"
               href="#"
               @click="_sidebarVisible=true">
                <h5><i class="fa fa-bars"></i> {{ _title }}</h5>
            </a>
        </div>
        <div class="card-body">
            <div v-if="_analyses === null" class="tab-content">
                <span class="spinner"></span>
                <div>Please wait...</div>
            </div>

            <div v-if="_analyses !== null && _analyses.length == 0" class="tab-content">
                This analysis reported no results for the selected datasets.
            </div>

            <div v-if="_analyses !== null && _analyses.length > 0" class="tab-content">
                <div class="tab-pane show active" role="tabpanel" aria-label="Tab showing a plot">
                    <div :class="['alert', message.alertClass]" v-for="message in _messages">
                        {{ message.message }}
                    </div>
                    <bokeh-plot
                        :plots="_plots"
                        :categories="_categories"
                        :data-sources="_dataSources"
                        :output-backend="_outputBackend"
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
                        <div class="btn-group ml-1" role="group" aria-label="Download formats">
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

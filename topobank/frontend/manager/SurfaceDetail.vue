<script>

import axios from "axios";

import {getIdFromUrl, subjectsToBase64} from "../utils/api";

import {
    BAccordion,
    BAccordionItem,
    BAlert,
    BButton,
    BButtonGroup,
    BCard,
    BCardBody,
    BCardHeader,
    BDropdown,
    BDropdownItem,
    BForm,
    BFormGroup,
    BFormInput,
    BFormTextarea,
    BModal,
    BSpinner,
    BTab,
    BTabs,
} from 'bootstrap-vue-next';

import BandwidthPlot from './BandwidthPlot.vue';
import DropZone from '../components/DropZone.vue';
import SurfaceProperties from './SurfaceProperties.vue';
import SurfacePermissions from './SurfacePermissions.vue';
import TopographyCard from "./TopographyCard.vue";

export default {
    name: 'surface-detail',
    components: {
        BandwidthPlot,
        BAccordion,
        BAccordionItem,
        BAlert,
        BButton,
        BButtonGroup,
        BCard,
        BCardBody,
        BCardHeader,
        BDropdown,
        BDropdownItem,
        BForm,
        BFormGroup,
        BFormInput,
        BFormTextarea,
        BModal,
        BSpinner,
        BTab,
        BTabs,
        DropZone,
        SurfaceProperties,
        SurfacePermissions,
        TopographyCard
    },
    props: {
        surfaceUrl: String,
        newTopographyUrl: {
            type: String,
            default: '/manager/api/topography/'
        },
        categories: {
            type: Object,
            default: {
                dum: 'Dummy data',
                exp: 'Experimental data',
                sim: 'Simulated data'
            }
        }
    },
    data() {
        return {
            _data: null,
            _showDeleteModal: false,
            _topographies: [],  // Topographies contained in this surface
            _versions: null  // Published versions of this topography
        }
    },
    mounted() {
        if (this._data === null) {
            this.updateCard();
        }
    },
    methods: {
        getOriginalSurfaceId() {
            if (this._data.publication === null) {
                return getIdFromUrl(this._data.url);
            } else {
                return getIdFromUrl(this._data.publication.original_surface);
            }
        },
        updateCard() {
            /* Fetch JSON describing the card */
            axios.get(`${this.surfaceUrl}?children=yes&permissions=yes`).then(response => {
                this._data = response.data;
                this._topographies = response.data.topography_set;
                this.updateVersions();
            });
        },
        updateVersions() {
            axios.get(`/go/api/publication/?original_surface=${this.getOriginalSurfaceId()}`).then(response => {
                this._versions = response.data;
                console.log(this._versions);
            });
        },
        filesDropped(files) {
            for (const file of files) {
                this.uploadNewTopography(file);
            }
        },
        uploadNewTopography(file) {
            axios.post(this.newTopographyUrl, {surface: this.surfaceUrl, name: file.name}).then(response => {
                let upload = response.data;
                upload.file = file;  // need to know which file to upload
                this._topographies.push(upload);
            });
        },
        topographyDeleted(url) {
            const index = this._topographies.findIndex(topography => topography.url === url);
            this._topographies.splice(index, 1);
        },
        topographyUpdated(index, topography) {
            this._topographies[index] = topography;
        },
        surfaceHrefForVersion(version) {
            return `http://localhost:8000/manager/html/surface/?surface=${getIdFromUrl(version.surface)}`;
        },
        htmlLinebreaks(s) {
            return s.replace(' ', '&nbsp;').replace('\n', '<br>');
        },
        deleteSurface() {
            axios.delete(this._data.url).then(response => {
                this.$emit('surface-deleted', this._data.url);
                window.location.href = `/manager/html/select/`;
            });
        }
    },
    computed: {
        category() {
            if (this._data === null) {
                return 'Unknown category';
            }
            const retval = this.categories[this._data.category];
            if (retval === undefined) {
                return 'Unknown category';
            }
            return retval;
        },
        base64Subjects() {
            return subjectsToBase64({surface: [this._data.id]});
        },
        versionString() {
            if (this._data === null || this._data.publication === null) {
                return "Work in progress";
            } else {
                return `Version ${this._data.publication.version} (${this._data.publication.datetime.slice(0, 10)})`;
            }
        },
        hrefOriginalSurface() {
            return `http://localhost:8000/manager/html/surface/?surface=${this.getOriginalSurfaceId()}`;
        }
    }
};
</script>

<template>
    <div class="container">
        <div class="row">
            <div class="col-12">
                <b-tabs class="nav-pills-custom"
                        content-class="w-100"
                        fill
                        pills
                        vertical>
                    <b-tab title="Measurements">
                        <drop-zone @files-dropped="filesDropped"></drop-zone>
                        <div v-for="(topography, index) in _topographies">
                            <topography-card :topography="topography"
                                             @topography-deleted="topographyDeleted"
                                             @topography-updated="topography => topographyUpdated(index, topography)">
                            </topography-card>
                        </div>
                    </b-tab>
                    <b-tab title="Bandwidths">
                        <b-card class="w-100">
                            <template #header>
                                <h5 class="float-start">Bandwidths</h5>
                            </template>
                            <b-card-body>
                                <b-alert v-if="_topographies.length == 0" info>
                                    This surface has no measurements yet.
                                </b-alert>
                                <b-alert v-if="_topographies.length > 0" secondary>
                                    This bandwidth plot shows the range of length scales that have been measured for
                                    this
                                    digital surface
                                    twin. Each of the blocks below represents one measurement. Part of the bandwidth
                                    shown
                                    may
                                    be unreliable
                                    due to the configured instrument's measurement capacities.
                                </b-alert>
                                <bandwidth-plot v-if="_topographies.length > 0"
                                                :topographies="_topographies">
                                </bandwidth-plot>
                            </b-card-body>
                        </b-card>
                    </b-tab>
                    <b-tab title="Properties">
                        <surface-properties v-if="_data !== null"
                                            :surface-url="_data.url"
                                            :name="_data.name"
                                            :description="_data.description"
                                            :category="_data.category"
                                            :tags="_data.tags">
                        </surface-properties>
                    </b-tab>
                    <b-tab v-if="_data !== null"
                           title="Permissions">
                        <surface-permissions v-if="_data.publication === null"
                                             :surface-url="_data.url"
                                             :permissions="_data.permissions">
                        </surface-permissions>
                        <b-card v-if="_data.publication !== null"
                                class="w-100">
                            <template #header>
                                <h5 class="float-start">Permissions</h5>
                            </template>
                            <b-card-body>
                                This dataset is published. It is visible to everyone (even without logging into the
                                system) and can no longer be modified.
                            </b-card-body>
                        </b-card>
                    </b-tab>
                    <b-tab v-if="_data !== null && _data.publication !== null"
                           title="How to cite">
                        <b-card class="w-100">
                            <template #header>
                                <h5 class="float-start">How to cite</h5>
                            </template>
                            <b-card-body>
                                <p class="mb-5">
                                    <img :src="`/static/images/cc/${_data.publication.license}.svg`"
                                         title="Dataset can be reused under the terms of a Creative Commons license."
                                         style="float:right"/>
                                    This dataset can be reused under the terms of a Creative Commons license.
                                    When reusing this dataset, please cite the original source.
                                </p>
                                <b-accordion>
                                    <b-accordion-item title="Citation" visible>
                                        <div v-html="_data.publication.citation.html"/>
                                    </b-accordion-item>
                                    <b-accordion-item title="RIS">
                                        <code>
                                            <pre>{{ _data.publication.citation.ris }}</pre>
                                        </code>
                                    </b-accordion-item>
                                    <b-accordion-item title="BibTeX">
                                        <code>
                                            <pre>{{ _data.publication.citation.bibtex }}</pre>
                                        </code>
                                    </b-accordion-item>
                                    <b-accordion-item title="BibLaTeX">
                                        <code>
                                            <pre>{{ _data.publication.citation.biblatex }}</pre>
                                        </code>
                                    </b-accordion-item>
                                </b-accordion>
                            </b-card-body>
                        </b-card>
                    </b-tab>
                    <template #tabs-end>
                        <hr/>
                        <div v-if="_data !== null"
                             class="card mt-2">
                            <div class="card-body">
                                <div>
                                    <span class="badge bg-secondary surface-category-headline">
                                        {{ category }}
                                    </span>
                                </div>
                                <div v-if="_data.publication !== null">
                                    <span class="badge bg-info">
                                        Published by {{ _data.publication.publisher.name }}
                                    </span>
                                </div>
                                <div>
                                    <span v-for="tag in _data.tags"
                                          class="badge bg-success">
                                        {{ tag.name }}
                                    </span>
                                </div>
                                <b-dropdown class="mt-2"
                                            variant="info"
                                            :text="versionString">
                                    <b-dropdown-item :href="hrefOriginalSurface"
                                                     :disabled="_data.publication === null">
                                        Work in progress
                                    </b-dropdown-item>
                                    <b-dropdown-item v-if="_versions === null">
                                        <b-spinner small/>
                                        Loading versions...
                                    </b-dropdown-item>
                                    <b-dropdown-item v-if="_versions !== null"
                                                     v-for="version in _versions"
                                                     :href="surfaceHrefForVersion(version)"
                                                     :disabled="_data.publication !== null && _data.publication.version === version.version">
                                        Version {{ version.version }}
                                    </b-dropdown-item>
                                </b-dropdown>
                                <div class="btn-group-vertical mt-2 w-100" role="group">
                                    <a :href="`/analysis/html/list/?subjects=${base64Subjects}`"
                                       class="btn btn-outline-secondary btn-block">
                                        Analyze this digital surface twin
                                    </a>

                                    <a :href="`${surfaceUrl}download/`"
                                       class="btn btn-outline-secondary btn-block">
                                        Download
                                    </a>

                                    <a :href="`${surfaceUrl.replace('/api/', '/html/')}publish/`"
                                       class="btn btn-outline-success btn-block">
                                        Publish
                                    </a>

                                    <a href="#"
                                       class="btn btn-outline-danger btn-block"
                                       @click="_showDeleteModal = true">
                                        Delete
                                    </a>
                                </div>
                            </div>
                        </div>
                    </template>
                </b-tabs>
            </div>
        </div>
    </div>
    <b-modal v-if="_data !== null"
             v-model="_showDeleteModal"
             @ok="deleteSurface"
             title="Delete digital surface twin">
        You are about to delete the digital surface twin with name <b>{{ _data.name }}</b> and all contained
        measurements. Are you sure you want to proceed?
    </b-modal>
</template>

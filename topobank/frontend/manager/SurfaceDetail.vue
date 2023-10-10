<script>

import axios from "axios";

import {subjectsToBase64} from "../utils/api";

import {
    BAlert,
    BButton,
    BButtonGroup,
    BCard,
    BCardBody,
    BCardHeader,
    BForm,
    BFormGroup,
    BFormInput,
    BFormTextarea,
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
        BAlert,
        BButton,
        BButtonGroup,
        BCard,
        BCardBody,
        BCardHeader,
        BForm,
        BFormGroup,
        BFormInput,
        BFormTextarea,
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
            _topographies: [],
        }
    },
    mounted() {
        if (this._data === null) {
            this.updateCard();
        }
    },
    methods: {
        updateCard() {
            /* Fetch JSON describing the card */
            axios.get(`${this.surfaceUrl}?children=yes&permissions=yes`).then(response => {
                this._data = response.data;
                this._topographies = response.data.topography_set;
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
                    <b-tab title="Permissions">
                        <surface-permissions v-if="_data !== null"
                                             :surface-url="_data.url"
                                             :permissions="_data.permissions">
                        </surface-permissions>
                    </b-tab>
                    <b-tab v-if="_data !== null && _data.is_published"
                           title="Authors">
                    </b-tab>
                    <b-tab v-if="_data !== null && _data.is_published"
                           title="License">
                    </b-tab>
                    <b-tab v-if="_data !== null && _data.is_published"
                           title="How to cite">
                    </b-tab>
                    <template #tabs-end>
                        <hr/>
                        <div v-if="_data !== null && _data.publication !== null"
                             class="btn-group">
                            <button type="button" id="versions-btn"
                                    class="btn btn-info dropdown-toggle"
                                    data-toggle="dropdown" aria-haspopup="true"
                                    aria-expanded="false">
                                ...this_version_label...
                                ...if version_badge_text...
                                <span class="badge bg-warning">...version_badge_text...</span>
                                ...endif...
                            </button>
                            <div class="dropdown-menu" id="versions-dropdown">
                                ...for version_item in version_dropdown_items...
                                <a class="dropdown-item{% if version_item.surface == surface %} disabled{% endif %}"
                                   href="...version_item.surface.get_absolute_url...">
                                    ...version_item.label...
                                </a>
                                ...endfor...
                            </div>
                        </div>
                        <div v-if="_data !== null"
                             class="card mt-2">
                            <div class="card-body">
                                <div>
                            <span class="badge bg-secondary surface-category-headline">
                                {{ category }}
                            </span>
                                </div>
                                <div>
                            <span v-for="tag in _data.tags"
                                  class="badge bg-success">
                                {{ tag.name }}
                            </span>
                                </div>
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
                                       class="btn btn-outline-danger btn-block">
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
</template>

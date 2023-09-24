<script>

import axios from "axios";

import DropZone from '../components/DropZone.vue';
import TopographyCard from "./TopographyCard.vue";

export default {
    name: 'surface-detail',
    components: {
        DropZone,
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
            axios.get(this.surfaceUrl).then(response => {
                this._data = response.data;
                this._topographies = response.data.topography_set;
                console.log(response.data);
            });
        },
        onFilesDropped(files) {
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
            console.log(index)
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
        }
    }
};
</script>

<template>
    <div class="row">

        <div class="col-12 col-sm-4 col-md-3 col-lg-2">

            <div class="nav nav-pills nav-pills-custom flex-column"
                 aria-orientation="vertical">

                <a class="nav-link mb-3 p-3 shadow active"
                   data-toggle="pill"
                   href="#topographies"
                   role="tab"
                   aria-selected="true">
                    Measurements
                </a>
                <a class="nav-link mb-3 p-3 shadow"
                   data-toggle="pill"
                   href="#bandwidths"
                   role="tab"
                   aria-selected="false">
                    Bandwidths
                </a>
                <a class="nav-link mb-3 p-3 shadow"
                   data-toggle="pill"
                   href="#description"
                   role="tab"
                   aria-selected="false">
                    Description
                </a>
                <a class="nav-link mb-3 p-3 shadow"
                   data-toggle="pill"
                   href="#permissions"
                   role="tab"
                   aria-selected="false">
                    Permissions
                </a>
                <a v-if="_data !== null && _data.is_published"
                   class="nav-link mb-3 p-3 shadow"
                   data-toggle="pill"
                   href="#authors"
                   role="tab"
                   aria-selected="false">
                    Authors
                </a>
                <a v-if="_data !== null && _data.is_published"
                   class="nav-link mb-3 p-3 shadow"
                   data-toggle="pill"
                   href="#license"
                   role="tab"
                   aria-selected="false">
                    License
                </a>
                <a v-if="_data !== null && _data.is_published"
                   class="nav-link mb-3 p-3 shadow"
                   data-toggle="pill"
                   href="#howtocite"
                   role="tab"
                   aria-selected="false">
                    How to cite
                </a>
            </div>
        </div>

        <div class="col-12 col-sm-5 col-md-6 col-lg-7">

            <div class="tab-content rounded tab-content-vertical-tabs">

                <div class="tab-pane fade active show" id="topographies">
                    <drop-zone @files-dropped="onFilesDropped"></drop-zone>
                    <div v-for="(topography, index) in _topographies">
                        <topography-card :topography="topography"
                                         @topography-deleted="topographyDeleted"
                                         @topography-updated="topography => topographyUpdated(index, topography)">
                        </topography-card>
                    </div>
                </div>

                <div class="tab-pane fade" id="bandwidths">
                    <div v-if="_data !== null && _data.num_topographies == 0"
                         class="alert alert-info">
                        This surface has no measurements yet.
                        You can add measurements by pressing the
                        <b>{% fa5_icon 'plus-square-o' %} Add measurement</b> button.
                    </div>
                    <div v-if="_data !== null && _data.num_topographies > 0"
                         class="alert alert-secondary">
                        This bandwidth plot shows the range of length scales that have been measured for this
                        digital surface
                        twin. Each of the blocks below represents one measurement. Part of the bandwidth shown may
                        be unreliable
                        due to the configured instrument's measurement capacities.
                    </div>
                </div>

                <div class="tab-pane p-2 fade" id="permissions">
                </div>
            </div>

        </div>

        <div class="col-12 col-sm-3 col-md-3 col-lg-3">
            <div class="row mb-3">
                <div class="col">
                    <div class="btn-group">
                        <button type="button" id="versions-btn"
                                class="btn btn-info dropdown-toggle
                        {% if version_dropdown_items|length == 1 %}disabled{% endif %}"
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
                </div>
            </div>
            <div class="row mb-3">
                <div class="col">
                    <div v-if="_data !== null"
                         class="card">
                        <div class="card-body">
                            <div>
                                <span class="badge bg-secondary surface-category-headline">
                                    {{ category }}
                                </span>
                            </div>
                            <div>
                                <span v-for="tag in _data.tags"
                                      class="badge bg-success">{{ tag.name }}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="row mb-3">
                <div class="col">
                    <div class="btn-group-vertical" role="group">
                        <a :href="`/analysis/html/list/?subjects=`"
                           class="btn btn-default btn-block">
                            Analyze this digital surface twin
                        </a>

                        <a href="`/manager/${surfaceId}/download`"
                           class="btn btn-default btn-block">
                            Download
                        </a>

                        <a href="#"
                           class="btn btn-outline-danger btn-block">
                            Delete
                        </a>
                    </div>
                </div>
            </div>
        </div>

    </div>
</template>

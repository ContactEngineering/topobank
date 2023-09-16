<script>

import DropZone from '../components/DropZone.vue';
import TopographyPropertiesCard from "./TopographyPropertiesCard.vue";
import TopographyUploadCard from "./TopographyUploadCard.vue";
import TopographyErrorCard from "topobank/manager/TopographyErrorCard.vue";

export default {
    name: 'surface-detail',
    components: {
        TopographyErrorCard,
        DropZone,
        TopographyPropertiesCard,
        TopographyUploadCard
    },
    inject: ['csrfToken'],
    props: {
        surfaceUrl: String,
        newTopographyUrl: {
            type: String,
            default: '/manager/api/topography/'
        },
    },
    data() {
        return {
            _data: null,
            _topographies: [],
            _uploads: []
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
            fetch(this.surfaceUrl, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                    'X-CSRFToken': this.csrfToken
                }
            })
                .then(response => response.json())
                .then(data => {
                    this._data = data;
                    this._topographies = data.topography_set;
                    console.log(data);
                });
        },
        onFilesDropped(files) {
            for (const file of files) {
                this.uploadNewTopography(file);
            }
        },
        uploadNewTopography(file) {
            console.log(file);
            fetch(this.newTopographyUrl, {
                method: 'POST',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                },
                body: JSON.stringify({surface: this.surfaceUrl, name: file.name}),
            })
                .then(response => response.json())
                .then(data => {
                    console.log(data);
                    data.file = file;
                    this._uploads.push(data);
                });
        },
        uploadSuccessful(topography) {
            this._uploads.splice(this._uploads.indexOf(topography), 1);
            this._topographies.push(topography);
        },
        topographyDeleted(topography) {
            this._topographies.splice(this._uploads.indexOf(topography), 1);
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
                    <topography-upload-card v-for="upload in _uploads"
                                            :name="upload.name"
                                            :file="upload.file"
                                            :post-data="upload.post_data"
                                            @upload-successful="(url) => uploadSuccessful(upload)">
                    </topography-upload-card>
                    <topography-error-card v-for="topography in _topographies"
                                           :url="topography.url"
                                           :name="topography.name"
                                           :error="topography.error">
                    </topography-error-card>
                    <topography-properties-card v-for="topography in _topographies"
                                                :data="topography"
                                                @topography-deleted="(url) => topographyDeleted(topography)">
                    </topography-properties-card>
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
                    <div class="card">
                        <div class="card-body">
                            <div>
                                <span class="badge bg-secondary surface-category-headline">
                                  ...surface.get_category_display|default_if_none:"category not defined yet"...
                                </span>
                            </div>
                            <div>
                                ...for tag in surface.tags.all...
                                <span class="badge bg-success">...tag.name...</span>
                                ...endfor...
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="row mb-3">
                <div class="col">

                    <a :href="`/analysis/html/list/?subjects=${subjects_b64}`"
                       class="btn btn-default btn-block btn-lg">
                        Analyze this digital surface twin
                    </a>

                    <a href="`/manager/${surfaceId}/download`"
                       class="btn btn-default btn-block btn-lg">
                        Download
                    </a>

                    <a href="#"
                       class="btn btn-outline-danger btn-block btn-lg">
                        Delete
                    </a>
                </div>
            </div>
        </div>

    </div>
</template>

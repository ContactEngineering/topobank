<script setup>

import axios from "axios";
import {computed, onMounted, ref} from "vue";

import {
    BAccordion,
    BAccordionItem,
    BAlert,
    BCard,
    BCardBody,
    BDropdown,
    BDropdownItem,
    BModal,
    BSpinner,
    BTab,
    BTabs,
} from 'bootstrap-vue-next';

import {getIdFromUrl, subjectsToBase64} from "../utils/api";

import BandwidthPlot from './BandwidthPlot.vue';
import DropZone from '../components/DropZone.vue';
import SurfaceProperties from './SurfaceProperties.vue';
import SurfacePermissions from './SurfacePermissions.vue';
import TopographyCard from "./TopographyCard.vue";

const props = defineProps({
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
});

const emit = defineEmits([
    'delete:surface'
])

const _data = ref(null);
const _showDeleteModal = ref(false);
const _topographies = ref([]);  // Topographies contained in this surface
const _versions = ref(null);  // Published versions of this topography

onMounted(() => {
    if (_data.value === null) {
        updateCard();
    }
});

function getOriginalSurfaceId() {
    if (_data.value.publication === null) {
        return getIdFromUrl(_data.value.url);
    } else {
        return getIdFromUrl(_data.value.publication.original_surface);
    }
}

function updateCard() {
    /* Fetch JSON describing the card */
    axios.get(`${props.surfaceUrl}?children=yes&permissions=yes`).then(response => {
        _data.value = response.data;
        _topographies.value = response.data.topography_set;
        updateVersions();
    });
}

function updateVersions() {
    axios.get(`/go/api/publication/?original_surface=${getOriginalSurfaceId()}`).then(response => {
        _versions.value = response.data;
    });
}

function filesDropped(files) {
    for (const file of files) {
        uploadNewTopography(file);
    }
}

function uploadNewTopography(file) {
    axios.post(props.newTopographyUrl, {surface: props.surfaceUrl, name: file.name}).then(response => {
        let upload = response.data;
        upload.file = file;  // need to know which file to upload
        _topographies.value.push(upload);
    });
}

function topographyDeleted(index) {
    _topographies.value[index] = null;
}

function topographyUpdated(index, topography) {
    _topographies.value[index] = topography;
}

function surfaceHrefForVersion(version) {
    return `http://localhost:8000/manager/html/surface/?surface=${getIdFromUrl(version.surface)}`;
}

function deleteSurface() {
    axios.delete(_data.value.url).then(response => {
        emit('delete:surface', _data.value.url);
        window.location.href = `/manager/html/select/`;
    });
}

const category = computed(() => {
    if (_data.value === null) {
        return 'Unknown category';
    }
    const retval = props.categories[_data.value.category];
    if (retval === undefined) {
        return 'Unknown category';
    }
    return retval;
});

const base64Subjects = computed(() => {
    return subjectsToBase64({surface: [_data.value.id]});
});

const versionString = computed(() => {
    if (_data.value === null || _data.value.publication === null) {
        return "Work in progress";
    } else {
        return `Version ${_data.value.publication.version} (${_data.value.publication.datetime.slice(0, 10)})`;
    }
});

const hrefOriginalSurface = computed(() => {
    return `http://localhost:8000/manager/html/surface/?surface=${getOriginalSurfaceId()}`;
});

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
                            <topography-card v-if="topography !== null"
                                             :topography="topography"
                                             @delete:topography="url => topographyDeleted(index)"
                                             @update:topography="newTopography => topographyUpdated(index, newTopography)">
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
                                    this digital surface twin. Each of the blocks below represents one measurement.
                                    Part of the bandwidth shown may be unreliable due to the configured instrument's
                                    measurement capacities.
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

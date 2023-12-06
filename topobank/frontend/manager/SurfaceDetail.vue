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
    BFormCheckbox,
    BModal,
    BSpinner,
    BTab,
    BTabs,
} from 'bootstrap-vue-next';

import {filterTopographyForPatchRequest, getIdFromUrl, subjectsToBase64} from "../utils/api";
import {ccLicenseInfo} from "../utils/data";

import BandwidthPlot from './BandwidthPlot.vue';
import DropZone from '../components/DropZone.vue';
import SurfaceProperties from './SurfaceProperties.vue';
import SurfacePermissions from './SurfacePermissions.vue';
import TopographyCard from "./TopographyCard.vue";
import TopographyPropertiesCard from "./TopographyPropertiesCard.vue";

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

// Data that is displayed or can be edited
const _data = ref(null);  // Surface data
const _permissions = ref(null);  // Permissions
const _topographies = ref([]);  // Topographies contained in this surface
const _versions = ref(null);  // Published versions of this surface

// GUI logic
const _errors = ref([]);   // Errors from saving batch edits
const _saving = ref(false);  // Saving batch edits
const _showDeleteModal = ref(false);  // Triggers delete modal
const _selected = ref([]);  // Selected topographies (for batch editing)

// Batch edit data
const _batchEditTopography = ref(emptyTopography());

function emptyTopography() {
    return {
        url: null,  // There is no representation of this topography on the server side
        name: null,
        channel_names: null,
        description: null,
        measurement_date: null,
        size_editable: true,
        size_x: null,
        size_y: null,
        unit_editable: true,
        unit: null,
        height_scale_editable: true,
        height_scale: null,
        fill_undefined_data_mode: null,
        detrend_mode: null,
        is_periodic: null,
        instrument_name: null,
        instrument_type: null,
        instrument_parameters: null,
        thumbnail: null,
        tags: []
    };
}

onMounted(() => {
    if (_data.value === null) {
        updateCard();
    }
});

function getSurfaceId() {
    return getIdFromUrl(_data.value.url);
}

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
        _permissions.value = response.data.permissions;
        _topographies.value = response.data.topography_set;
        _selected.value = new Array(_topographies.value.length).fill(false);  // Nothing is selected
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
        _topographies.value.push(upload);  // this will trigger showing a topography-upload-card
        _selected.value.push(false);  // initially unselected
    });
}

function deleteTopography(index) {
    _topographies.value[index] = null;
}

function saveBatchEdit(topography) {
    // Trigger saving spinner
    _saving.value = true;

    // Clear all null fields
    const cleanedBatchEditTopography = filterTopographyForPatchRequest(topography);

    // Clear possible errors
    _errors.value = [];

    // Update all topographies and issue patch request
    for (const i in _topographies.value) {
        if (_selected.value[i]) {
            const t = {
                ..._topographies.value[i],
                ...cleanedBatchEditTopography
            }

            axios.patch(t.url, filterTopographyForPatchRequest(t)).then(response => {
                _topographies.value[i] = response.data;
            }).catch(error => {
                _errors.value.push(error);
                console.log(_errors);
            });
        }
    }

    // Reset selection
    _selected.value.fill(false);

    // Reset the batch edit topography template
    _batchEditTopography.value = emptyTopography();

    // Saving is done
    _saving.value = false;
}

function discardBatchEdit() {
    // Reset selection
    _selected.value.fill(false);

    // Reset the batch edit topography template
    _batchEditTopography.value = emptyTopography();
}

function surfaceHrefForVersion(version) {
    return `/manager/html/surface/?surface=${getIdFromUrl(version.surface)}`;
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
    return `/manager/html/surface/?surface=${getOriginalSurfaceId()}`;
});

const publishUrl = computed(() => {
    return `/go/publish/${getSurfaceId()}/`;
});

const isEditable = computed(() => {
    return _data.value !== null && _data.value.permissions.current_user.permission !== 'view';
});

const isPublication = computed(() => {
    return _data.value !== null && _data.value.publication !== null;
});

const anySelected = computed(() => {
    return _selected.value.reduce((x, y) => x || y, false);
});

const someSelected = computed(() => {
    const nbSelected = _selected.value.reduce((x, y) => x + (y ? 1 : 0), 0);
    const nbTopographies = _topographies.value.reduce((x, y) => x + (y != null ? 1 : 0), 0);
    return nbSelected > 0 && nbSelected < nbTopographies;
});

const allSelected = computed({
    get() {
        return _selected.value.reduce((x, y) => x && y, true);
    },
    set(value) {
        _selected.value.fill(value);
    }
});

</script>

<template>
    <div class="container">
        <div class="row">
            <div class="col-12">
                <b-alert v-for="error in _errors"
                         variant="danger">
                    {{ error.message }}
                </b-alert>
                <div v-if="_data === null"
                     class="card mb-1">
                    <div class="card-body">
                        <b-spinner small></b-spinner>
                        Querying digital surface twin data, please wait...
                    </div>
                </div>
                <b-tabs v-if="_data !== null"
                        class="nav-pills-custom"
                        content-class="w-100"
                        fill
                        pills
                        vertical>
                    <b-tab title="Measurements">
                        <drop-zone v-if="isEditable && !anySelected"
                                   @files-dropped="filesDropped">
                        </drop-zone>
                        <topography-properties-card v-if="anySelected"
                                                    :batch-edit="true"
                                                    :saving="_saving"
                                                    v-model:topography="_batchEditTopography"
                                                    @save:edit="saveBatchEdit"
                                                    @discard:edit="discardBatchEdit">
                        </topography-properties-card>
                        <div v-if="isEditable && _topographies.length > 0"
                             class="d-flex mb-1">
                            <b-card>
                                <b-form-checkbox size="sm"
                                                 :indeterminate="someSelected"
                                                 v-model="allSelected">
                                    Select all
                                </b-form-checkbox>
                            </b-card>
                        </div>
                        <div v-for="(topography, index) in _topographies">
                            <topography-card v-if="topography !== null"
                                             :selectable="isEditable"
                                             :topography-url="topography.url"
                                             :disabled="!isEditable"
                                             @delete:topography="() => deleteTopography(index)"
                                             v-model:topography="_topographies[index]"
                                             v-model:selected="_selected[index]">
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
                                            :tags="_data.tags"
                                            :permission="_permissions.current_user.permission">
                        </surface-properties>
                    </b-tab>
                    <b-tab v-if="_data !== null"
                           title="Permissions">
                        <surface-permissions v-if="_data.publication === null"
                                             :surface-url="_data.url"
                                             v-model:permissions="_permissions">
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
                    <b-tab v-if="isPublication"
                           title="How to cite">
                        <b-card class="w-100">
                            <template #header>
                                <h5 class="float-start">How to cite</h5>
                            </template>
                            <b-card-body>
                                <p class="mb-5">
                                    <a :href="ccLicenseInfo[_data.publication.license].descriptionUrl">
                                        <img :src="`/static/images/cc/${_data.publication.license}.svg`"
                                             :title="`Dataset can be reused under the terms of the ${ccLicenseInfo[_data.publication.license].title}.`"
                                             style="float:right; margin-left: 0.25rem;"/>
                                    </a>
                                    This dataset can be reused under the terms of the
                                    <a :href="ccLicenseInfo[_data.publication.license].descriptionUrl">
                                        {{ ccLicenseInfo[_data.publication.license].title }}
                                    </a>.
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
                                <b-dropdown v-if="_versions === null || _versions.length > 0"
                                            class="mt-2"
                                            variant="info"
                                            :text="versionString">
                                    <b-dropdown-item
                                        v-if="_data.publication === null || _data.publication.has_access_to_original_surface"
                                        :href="hrefOriginalSurface"
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

                                    <a v-if="!isPublication"
                                       :href="publishUrl"
                                       class="btn btn-outline-success btn-block">
                                        Publish
                                    </a>

                                    <a v-if="_versions === null || _versions.length === 0"
                                       href="#"
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

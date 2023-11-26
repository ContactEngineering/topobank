<script setup>

import axios from "axios";
import {cloneDeep} from "lodash";
import {computed, ref, watch} from "vue";

import {
    BAlert, BFormCheckbox, BFormInput, BFormSelect, BFormTags, BFormTextarea, BModal, BSpinner
} from 'bootstrap-vue-next';

import {filterTopographyForPatchRequest, subjectsToBase64} from "../utils/api";

import TopographyBadges from "./TopographyBadges.vue";

const props = defineProps({
    batchEdit: {type: Boolean, default: false},
    defaultResolutionUnit: {type: String, default: 'nm'},
    defaultResolutionValue: {type: Number, value: 300},
    defaultTipRadiusUnit: {type: String, default: 'nm'},
    defaultTipRadiusValue: {type: Number, value: 30},
    disabled: {type: Boolean, default: false},
    enlarged: {type: Boolean, default: false},
    saving: {type: Boolean, default: false},
    selectable: {type: Boolean, default: false},
    selected: {type: Boolean, default: false},
    topography: {type: Object, default: null},
    topographyUrl: {type: String, default: null}
});

const emit = defineEmits([
    'delete:topography',
    'update:topography',
    'update:selected',
    'save:edit',
    'discard:edit'
]);

const selectedModel = computed({
    get() {
        return props.selected;
    },
    set(value) {
        emit('update:selected', value);
    }
});

// Switches controlling visibility
const _descriptionVisible = ref(props.enlarged);
const _filtersVisible = ref(props.enlarged);
const _instrumentVisible = ref(props.enlarged);

// GUI logic
const _editing = ref(props.batchEdit);
const _error = ref(null);
const _saving = ref(false);
const _showDeleteModal = ref(false);

// Old topography data (used to restore data when "Discard" is clicked)
let _savedTopography = null;

// Choices for select form components
const _units = [
    {value: "km", text: 'km'},
    {value: "m", text: 'm'},
    {value: "mm", text: 'mm'},
    {value: "µm", text: 'µm'},
    {value: "nm", text: 'nm'},
    {value: "Å", text: 'Å'},
    {value: "pm", text: 'pm'}
];
const _instrumentChoices = [
    {value: 'undefined', text: 'Instrument of unknown type - all data considered as reliable'},
    {value: 'microscope-based', text: 'Microscope-based instrument with known resolution'},
    {value: 'contact-based', text: 'Contact-based instrument with known tip radius'}
];
const _detrendChoices = [
    {value: 'center', text: 'No detrending, but subtract mean height'},
    {value: 'height', text: 'Remove tilt'},
    {value: 'curvature', text: 'Remove curvature and tilt'}
];
const _undefinedDataChoices = [
    {value: 'do-not-fill', text: 'Do not fill undefined data points'},
    {value: 'harmonic', text: 'Interpolate undefined data points with harmonic functions'}
];

function saveEdits() {
    if (props.batchEdit) {
        emit('save:edit', props.topography);
    } else {
        _editing.value = false;
        _saving.value = true;
        axios.patch(props.topographyUrl, filterTopographyForPatchRequest(props.topography)).then(response => {
            _error.value = null;
            emit('update:topography', response.data);
        }).catch(error => {
            _error.value = error;
            emit('update:topography', _savedTopography);
        }).finally(() => {
            _saving.value = false;
        });
    }
}

function discardEdits() {
    if (props.batchEdit) {
        // Tell upstream components that discard was click
        emit('discard:edit');
    } else {
        // Turn off editing and restore prior state
        _editing.value = false;
        emit('update:topography', _savedTopography);
    }
}

function deleteTopography() {
    axios.delete(props.topographyUrl).then(response => {
        emit('delete:topography', props.topographyUrl);
    }).catch(error => {
        _error.value = error;
    });
}

function forceInspect() {
    axios.post(`${props.topographyUrl}force-inspect/`).then(response => {
        emit('update:topography', response.data);
    }).catch(error => {
        _error.value = error;
    });
}

const isMetadataIncomplete = computed(() => {
    if (props.topography != null && props.topography.is_metadata_complete !== undefined) {
        return !props.topography.is_metadata_complete;
    } else {
        return true;
    }
});

const channelOptions = computed(() => {
    if (props.topography == null) {
        return [];
    }

    let options = [];
    for (const [channelIndex, channelName] of props.topography.channel_names.entries()) {
        const [name, unit] = channelName;
        if (unit == null) {
            options.push({value: channelIndex, text: name});
        } else {
            options.push({value: channelIndex, text: `${name} (${unit})`});
        }
    }
    return options;
});

// Select class for highlighting input fields. Field are highlighted
// * danger/red if they are necessary for metadata to be complete
// * success/green if they have value during batch editing, i.e. if that value will be updated for all selected
//   topographies
function highlightInput(key) {
    let highlightMandatoryInput = {};
    if (['size_x', 'size_y', 'unit', 'height_scale'].includes(key)) {
        highlightMandatoryInput = {'bg-danger-subtle': !props.batchEdit && props.topography[key] == null};
    }
    return {
        ...highlightMandatoryInput,
        'bg-success-subtle': props.batchEdit
            && props.topography[key] != null
            && (props.topography[key].length === undefined || props.topography[key].length > 0)  // tags cannot be null
    };
}

// Transform instrument parameters to a model
function instrumentParameterModel(key1, key2) {
    return computed({
        get() {
            if (props.topography.instrument_parameters != null) {
                if (props.topography.instrument_parameters[key1] != null) {
                    return props.topography.instrument_parameters[key1][key2];
                }
            }
            return null;
        },
        set(v) {
            let t = cloneDeep(props.topography);
            if (t.instrument_parameters == null) {
                t.instrument_parameters = {[key1]: {[key2]: v}};
            } else if (t.instrument_parameters[key1] == null) {
                t.instrument_parameters[key1] = {[key2]: v};
            } else {
                t.instrument_parameters[key1][key2] = v;
            }
            emit('update:topography', t);
        }
    });
}

const instrumentParametersResolutionValue = instrumentParameterModel('resolution', 'value');
const instrumentParametersResolutionUnit = instrumentParameterModel('resolution', 'unit');
const instrumentParametersTipRadiusValue = instrumentParameterModel('tip_radius', 'value');
const instrumentParametersTipRadiusUnit = instrumentParameterModel('tip_radius', 'unit');

</script>

<template>
    <div class="card mb-1"
         :class="{ 'border-danger border-2': !batchEdit && isMetadataIncomplete, 'bg-secondary-subtle': selected, 'bg-warning-subtle': batchEdit }">
        <div class="card-header">
            <div
                v-if="!batchEdit && topography != null"
                class="d-flex float-start">
                <b-form-checkbox v-if="selectable" v-model="selectedModel"
                                 :disabled="_editing"
                                 size="sm">
                </b-form-checkbox>
                <b-form-select v-if="topography.channel_names != null && topography.channel_names.length > 0"
                               :options="channelOptions"
                               v-model="topography.data_source"
                               :disabled="!_editing"
                               size="sm">
                </b-form-select>
            </div>
            <div v-if="batchEdit"
                 class="float-start fs-5 fw-bold">
                Batch edit
            </div>
            <div v-if="!batchEdit && topography != null && !_editing && !_saving && !saving && !enlarged"
                 class="btn-group btn-group-sm float-end">
                <a v-if="!selected"
                   class="btn btn-outline-secondary float-end ms-2"
                   :href="`/manager/html/topography/?topography=${topography.id}`">
                    <i class="fa fa-expand"></i>
                </a>
                <button v-if="selected"
                        class="btn btn-outline-secondary float-end ms-2"
                        disabled>
                    <i class="fa fa-expand"></i>
                </button>
            </div>
            <div v-if="!batchEdit && topography != null && !_editing && !_saving && !saving"
                 class="btn-group btn-group-sm float-end">
                <button v-if="!disabled"
                        class="btn btn-outline-secondary"
                        :disabled="selected"
                        @click="_savedTopography = cloneDeep(topography); _editing = true">
                    <i class="fa fa-pen"></i>
                </button>
                <a v-if="!enlarged && !selected"
                   class="btn btn-outline-secondary"
                   :href="topography.datafile">
                    <i class="fa fa-download"></i>
                </a>
                <button v-if="!disabled && selected"
                        class="btn btn-outline-secondary"
                        disabled>
                    <i class="fa fa-download"></i>
                </button>
                <button v-if="!disabled"
                        class="btn btn-outline-secondary"
                        :disabled="selected">
                    <i class="fa fa-refresh"
                       @click="forceInspect"></i>
                </button>
                <button v-if="!disabled && !enlarged"
                        :disabled="selected"
                        class="btn btn-outline-secondary"
                        @click="_showDeleteModal = true">
                    <i class="fa fa-trash"></i>
                </button>
            </div>
            <div v-if="_editing || _saving || saving"
                 class="btn-group btn-group-sm float-end">
                <button v-if="_editing"
                        class="btn btn-danger"
                        @click="discardEdits">
                    Discard
                </button>
                <button class="btn btn-success"
                        @click="saveEdits">
                    <b-spinner small v-if="_saving || saving"></b-spinner>
                    SAVE
                </button>
            </div>
            <div v-if="!batchEdit"
                 class="btn-group btn-group-sm float-end me-2">
                <a class="btn btn-outline-secondary"
                   :href="`/analysis/html/list/?subjects=${subjectsToBase64({topography: [topography.id]})}`">
                    Analyze
                </a>
            </div>
            <div class="btn-group btn-group-sm float-end me-2">
                <button v-if="!enlarged"
                        class="btn btn-outline-secondary"
                        :class="{ active: _descriptionVisible }"
                        @click="_descriptionVisible = !_descriptionVisible">
                    Description
                </button>
                <button v-if="!enlarged"
                        class="btn btn-outline-secondary"
                        :class="{ active: _instrumentVisible }"
                        @click="_instrumentVisible = !_instrumentVisible">
                    Instrument
                </button>
                <button v-if="!enlarged"
                        class="btn btn-outline-secondary"
                        :class="{ active: _filtersVisible }"
                        @click="_filtersVisible = !_filtersVisible">
                    Filters
                </button>
            </div>
        </div>
        <div class="card-body">
            <b-alert :model-value="_error != null"
                     variant="danger">
                {{ _error.message }}
            </b-alert>
            <div v-if="topography == null"
                 class="tab-content">
                <b-spinner small></b-spinner>
                Please wait...
            </div>
            <div v-if="topography != null"
                 class="container">
                <div class="row">
                    <div v-if="topography.thumbnail != null"
                         class="col-2">
                        <a :href="`/manager/html/topography/?topography=${topography.id}`">
                            <img class="img-thumbnail mw-100"
                                 :src="topography.thumbnail">
                        </a>
                    </div>
                    <div :class="{ 'col-10': topography.thumbnail != null, 'col-12': topography.thumbnail == null }">
                        <div class="container">
                            <div class="row">
                                <div class="col-6">
                                    <label for="input-name">Name</label>
                                    <b-form-input id="input-name"
                                                  v-model="topography.name"
                                                  :class="highlightInput('name')"
                                                  :disabled="!_editing || batchEdit">
                                    </b-form-input>
                                </div>
                                <div class="col-3">
                                    <label for="input-measurement-date">Date</label>
                                    <b-form-input id="input-measurement-date"
                                                  type="date"
                                                  v-model="topography.measurement_date"
                                                  :class="highlightInput('measurement_date')"
                                                  :disabled="!_editing">
                                    </b-form-input>
                                </div>
                                <div class="col-3">
                                    <label for="input-periodic">Flags</label>
                                    <b-form-checkbox id="input-periodic"
                                                     v-model="topography.is_periodic"
                                                     :class="highlightInput('is_periodic')"
                                                     :disabled="!_editing || !topography.is_periodic_editable">
                                        Data is periodic
                                    </b-form-checkbox>
                                </div>
                            </div>
                            <div class="row">
                                <div class="col-8">
                                    <label for="input-physical-size">Physical size</label>
                                    <div class="input-group mb-1">
                                        <b-form-input id="input-physical-size"
                                                      type="number"
                                                      step="any"
                                                      :class="highlightInput('size_x')"
                                                      v-model="topography.size_x"
                                                      :disabled="!_editing || !topography.size_editable">
                                        </b-form-input>
                                        <span v-if="batchEdit || topography.resolution_y != null"
                                              class="input-group-text">
                                            &times;
                                        </span>
                                        <b-form-input v-if="batchEdit || topography.resolution_y != null"
                                                      type="number"
                                                      step="any"
                                                      :class="highlightInput('size_y')"
                                                      v-model="topography.size_y"
                                                      :disabled="!_editing || !topography.size_editable">
                                        </b-form-input>
                                        <b-form-select class="unit-select"
                                                       :options="_units"
                                                       v-model="topography.unit"
                                                       :class="highlightInput('unit')"
                                                       :disabled="!_editing || !topography.unit_editable">
                                        </b-form-select>
                                    </div>
                                    <small v-if="batchEdit">
                                        When batch editing line scans, only the first entry of the physical size
                                        will be used to set the overall length of the line scan.
                                    </small>
                                </div>
                                <div class="col-4">
                                    <label for="input-physical-size">Height scale</label>
                                    <b-form-input id="input-physical-size"
                                                  type="number"
                                                  step="any"
                                                  :class="highlightInput('height_scale')"
                                                  v-model="topography.height_scale"
                                                  :disabled="!_editing || !topography.height_scale_editable">
                                    </b-form-input>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="row mt-2">
                    <div class="col-12">
                        <div v-if="_descriptionVisible" class="container">
                            <div class="row">
                                <div class="col-12">
                                    <label for="input-descriptions">Description</label>
                                    <b-form-textarea id="input-description"
                                                     placeholder="Please provide a short description of this measurement"
                                                     v-model="topography.description"
                                                     :class="highlightInput('description')"
                                                     :disabled="!_editing"
                                                     rows="5">
                                    </b-form-textarea>
                                </div>
                            </div>
                            <div class="row">
                                <div class="col-12">
                                    <label for="input-tags">Tags</label>
                                    <b-form-tags id="input-tags"
                                                 tag-pills
                                                 :class="highlightInput('tags')"
                                                 v-model="topography.tags"
                                                 :disabled="!_editing">
                                    </b-form-tags>
                                </div>
                            </div>
                        </div>
                        <div v-if="_instrumentVisible" class="container">
                            <div class="row">
                                <div class="col-6">
                                    <label for="input-instrument-name">Instrument name</label>
                                    <b-form-input id="input-instrument-name"
                                                  :class="highlightInput('instrument_name')"
                                                  v-model="topography.instrument_name"
                                                  :disabled="!_editing">
                                    </b-form-input>
                                </div>
                                <div class="col-6">
                                    <label for="input-instrument-type">Instrument type</label>
                                    <b-form-select id="input-instrument-type"
                                                   :options="_instrumentChoices"
                                                   :class="highlightInput('instrument_type')"
                                                   v-model="topography.instrument_type"
                                                   :disabled="!_editing">
                                    </b-form-select>
                                </div>
                            </div>
                            <div v-if="topography.instrument_type == 'microscope-based'" class="row">
                                <div class="col-12 mt-1">
                                    <label for="input-instrument-resolution">Lateral instrument resolution</label>
                                    <div id="input-instrument-resolution" class="input-group mb-1">
                                        <b-form-input type="number"
                                                      step="any"
                                                      :placeholder="defaultResolutionValue"
                                                      :class="highlightInput('instrument_parameters')"
                                                      v-model="instrumentParametersResolutionValue"
                                                      :disabled="!_editing">
                                        </b-form-input>
                                        <b-form-select style="width: 100px;"
                                                       :options="_units"
                                                       :placeholder="defaultResolutionUnit"
                                                       :class="highlightInput('instrument_parameters')"
                                                       v-model="instrumentParametersResolutionUnit"
                                                       :disabled="!_editing">
                                        </b-form-select>
                                    </div>
                                </div>
                            </div>
                            <div v-if="topography.instrument_type == 'contact-based'" class="row">
                                <div class="col-12 mt-1">
                                    <label for="input-instrument-tip-radius">Probe tip radius</label>
                                    <div id="input-instrument-tip-radius" class="input-group mb-1">
                                        <b-form-input type="number"
                                                      step="any"
                                                      :placeholder="defaultTipRadiusValue"
                                                      :class="highlightInput('instrument_parameters')"
                                                      v-model="instrumentParametersTipRadiusValue"
                                                      :disabled="!_editing">
                                        </b-form-input>
                                        <b-form-select style="width: 100px;"
                                                       :options="_units"
                                                       :placeholder="defaultTipRadiusUnit"
                                                       :class="highlightInput('instrument_parameters')"
                                                       v-model="instrumentParametersTipRadiusUnit"
                                                       :disabled="!_editing">
                                        </b-form-select>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div v-if="_filtersVisible" class="container">
                            <div class="row">
                                <div class="col-6 mt-1">
                                    <label for="input-detrending">Detrending</label>
                                    <div id="input-detrending" class="input-group mb-1">
                                        <b-form-select :options="_detrendChoices"
                                                       v-model="topography.detrend_mode"
                                                       :class="highlightInput('detrend_mode')"
                                                       :disabled="!_editing">
                                        </b-form-select>
                                    </div>
                                </div>
                                <div class="col-6 mt-1">
                                    <label for="input-undefined-data">Undefined/missing data</label>
                                    <div id="input-undefined-data" class="input-group mb-1">
                                        <b-form-select :options="_undefinedDataChoices"
                                                       v-model="topography.fill_undefined_data_mode"
                                                       :class="highlightInput('fill_undefined_data_mode')"
                                                       :disabled="!_editing">
                                        </b-form-select>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <div v-if="!batchEdit && !enlarged"
             class="card-footer">
            <topography-badges :topography="topography"></topography-badges>
        </div>
        <div v-if="batchEdit"
             class="card-footer">
            <small>You are about to change the metadata of multiple measurements. Note that batch editing will only
                update entries that are editable, i.e. that are not fixed by the contents of the data file. This
                includes physical sizes, unit or the height scale and may differ between the measurements you are
                updating.</small>
        </div>
    </div>
    <b-modal v-if="topography != null"
             v-model="_showDeleteModal"
             @ok="deleteTopography"
             title="Delete measurement">
        You are about to delete the measurement with name <b>{{ topography.name }}</b>.
        Are you sure you want to proceed?
    </b-modal>
</template>

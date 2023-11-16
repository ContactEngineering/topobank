<script setup>

import axios from "axios";
import {cloneDeep} from "lodash";
import {computed, onMounted, ref, watch} from "vue";

import {
    BAlert, BFormCheckbox, BFormInput, BFormSelect, BFormTags, BFormTextarea, BModal, BSpinner
} from 'bootstrap-vue-next';

import TopographyBadges from "./TopographyBadges.vue";

const props = defineProps({
    defaultResolutionUnit: {
        type: String,
        default: 'nm'
    },
    defaultResolutionValue: {
        type: Number,
        value: 300
    },
    defaultTipRadiusUnit: {
        type: String,
        default: 'nm'
    },
    defaultTipRadiusValue: {
        type: Number,
        value: 30
    },
    disabled: {
        type: Boolean,
        default: false
    },
    enlarged: {
        type: Boolean,
        default: false
    },
    selectable: {
        type: Boolean,
        default: false
    },
    topography: {
        type: Object,
        default: null
    },
    topographyUrl: {
        type: String,
        default: null
    }
});

const emit = defineEmits([
    'delete:topography',
    'update:topography',
    'select:topography'
]);

const _topography = ref(null);
const _descriptionVisible = ref(props.enlarged);
const _editing = ref(false);
const _error = ref(null);
const _filtersVisible = ref(props.enlarged);
const _instrument_parameters_resolution_value = ref(null);
const _instrument_parameters_resolution_unit = ref(null);
const _instrument_parameters_tip_radius_value = ref(null);
const _instrument_parameters_tip_radius_unit = ref(null);
const _instrumentVisible = ref(props.enlarged);
const _saving = ref(false);
const _selected = ref(false);
const _topographyUrl = ref(props.topographyUrl === null ? props.topography.url : props.topographyUrl);
const _savedTopography = ref(null);
const _showDeleteModal = ref(false);

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

onMounted(() => {
    if (props.topography !== null) {
        mogrifyDataFromGETRequest(props.topography);
    } else {
        updateCard();
    }
});

function updateCard() {
    /* Fetch JSON describing the card */
    axios.get(_topographyUrl).then(response => {
        _topography.value = response.data;
        _topographyUrl.value = response.data.url;
    });
}

function mogrifyDataFromGETRequest(data) {
    // Get data object
    _topography.value = data;
    _topographyUrl.value = data.url;

    // Flatten instrument parameters
    if (data.instrument_parameters.resolution !== undefined) {
        _instrument_parameters_resolution_value.value = data.instrument_parameters.resolution.value;
        _instrument_parameters_resolution_unit.value = data.instrument_parameters.resolution.unit;
    } else {
        _instrument_parameters_resolution_value.value = props.defaultResolutionValue;
        _instrument_parameters_resolution_unit.value = props.defaultResolutionUnit;
    }

    if (data.instrument_parameters.tip_radius !== undefined) {
        _instrument_parameters_tip_radius_value.value = data.instrument_parameters.tip_radius.value;
        _instrument_parameters_tip_radius_unit.value = data.instrument_parameters.tip_radius.unit;
    } else {
        _instrument_parameters_tip_radius_value.value = props.defaultTipRadiusValue;
        _instrument_parameters_tip_radius_unit.value = props.defaultTipRadiusUnit;
    }
}

function mogrifyDataForPATCHRequest() {
    // Copy writable entries
    let writeableEntries = [
        'description', 'instrument_name', 'instrument_parameters', 'instrument_type', 'is_periodic',
        'measurement_date', 'name', 'tags', 'detrend_mode', 'fill_undefined_data_mode', 'data_source'
    ];
    if (_topography.value.size_editable) {
        writeableEntries.push('size_x', 'size_y');
    }
    if (_topography.value.unit_editable) {
        writeableEntries.push('unit');
    }
    if (_topography.value.height_scale_editable) {
        writeableEntries.push('height_scale');
    }

    let returnDict = {};
    for (const e of writeableEntries) {
        returnDict[e] = _topography.value[e];
    }

    // Unflatten instrument parameters
    returnDict.instrument_parameters = {
        resolution: {
            value: _instrument_parameters_resolution_value.value,
            unit: _instrument_parameters_resolution_unit.value
        },
        tip_radius: {
            value: _instrument_parameters_tip_radius_value.value,
            unit: _instrument_parameters_tip_radius_unit.value
        },
    }

    // Uncomment to simulate error on PATCH
    // returnDict['thumbnail'] = 'def';

    return returnDict;
}

function saveCard() {
    _editing.value = false;
    _saving.value = true;
    axios.patch(_topographyUrl.value, mogrifyDataForPATCHRequest()).then(response => {
        _error.value = null;
        emit('update:topography', response.data);
        mogrifyDataFromGETRequest(response.data);
    }).catch(error => {
        _error.value = error;
        _topography.value = _savedTopography.value;
    }).finally(() => {
        _saving.value = false;
    });
}

function deleteTopography() {
    axios.delete(_topographyUrl.value);
    emit('delete:topography', _topographyUrl.value);
}

function forceInspect() {
    axios.post(`${_topographyUrl.value}force-inspect/`).then(response => {
        emit('update:topography', response.data);
    });
}

const isMetadataIncomplete = computed(() => {
    if (_topography.value !== null && _topography.value.is_metadata_complete !== undefined) {
        return !_topography.value.is_metadata_complete;
    } else {
        return true;
    }
});

const channelOptions = computed(() => {
    if (_topography.value === null) {
        return [];
    }

    let options = [];
    for (const [channelIndex, channelName] of _topography.value.channel_names.entries()) {
        const [name, unit] = channelName;
        if (unit === null) {
            options.push({value: channelIndex, text: name});
        } else {
            options.push({value: channelIndex, text: `${name} (${unit})`});
        }
    }
    return options;
});

watch(_selected, (newValue, oldValue) => {
    emit('select:topography', newValue);
});

</script>

<template>
    <div class="card mb-1" :class="{ 'bg-danger-subtle': isMetadataIncomplete, 'bg-secondary-subtle': _selected }">
        <div class="card-header">
            <b-form-group v-if="_topography !== null && _topography.channel_names.length > 0"
                          label-size="sm"
                          class="d-flex float-start">
                <b-form-checkbox v-if="selectable" v-model="_selected"
                                 :disabled="_editing"
                                 size="sm">
                </b-form-checkbox>
                <b-form-select :options="channelOptions"
                               v-model="_topography.data_source"
                               :disabled="!_editing"
                               size="sm">
                </b-form-select>
            </b-form-group>
            <div v-if="_topography !== null && !_editing && !_saving && !enlarged"
                 class="btn-group btn-group-sm float-end">
                <a v-if="!_selected"
                   class="btn btn-outline-secondary float-end ms-2"
                   :href="`/manager/html/topography/?topography=${_topography.id}`">
                    <i class="fa fa-expand"></i>
                </a>
                <button v-if="_selected"
                        class="btn btn-outline-secondary float-end ms-2"
                        disabled>
                    <i class="fa fa-expand"></i>
                </button>
            </div>
            <div v-if="_topography !== null && !_editing && !_saving"
                 class="btn-group btn-group-sm float-end">
                <button class="btn btn-outline-secondary"
                        :disabled="disabled || _selected"
                        @click="_savedTopography = cloneDeep(_topography); _editing = true">
                    <i class="fa fa-pen"></i>
                </button>
                <a v-if="!enlarged && !_selected"
                   class="btn btn-outline-secondary"
                   :href="_topography.datafile">
                    <i class="fa fa-download"></i>
                </a>
                <button v-if="_selected"
                        class="btn btn-outline-secondary"
                        disabled>
                    <i class="fa fa-download"></i>
                </button>
                <button class="btn btn-outline-secondary"
                        :disabled="disabled || _selected">
                    <i class="fa fa-refresh"
                       @click="forceInspect"></i>
                </button>
                <button v-if="!enlarged"
                        :disabled="disabled || _selected"
                        class="btn btn-outline-secondary"
                        @click="_showDeleteModal = true">
                    <i class="fa fa-trash"></i>
                </button>
            </div>
            <div v-if="_editing || _saving"
                 class="btn-group btn-group-sm float-end">
                <button v-if="_editing"
                        class="btn btn-danger"
                        @click="_editing = false; _topography = _savedTopography">
                    Discard
                </button>
                <button class="btn btn-success"
                        @click="saveCard">
                    <b-spinner small v-if="_saving"></b-spinner>
                    SAVE
                </button>
            </div>
            <div class="btn-group btn-group-sm float-end me-2">
                <button v-if="!enlarged"
                        class="btn btn-outline-secondary"
                        :class="{ active: _descriptionVisible }"
                        @click="_descriptionVisible = !_descriptionVisible">
                    Properties
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
            <b-alert :model-value="_error !== null"
                     variant="danger">
                {{ _error }}
            </b-alert>
            <div v-if="_topography === null"
                 class="tab-content">
                <b-spinner small></b-spinner>
                Please wait...
            </div>
            <div v-if="_topography !== null"
                 class="container">
                <div class="row">
                    <div class="col-2">
                        <a :href="`/manager/html/topography/?topography=${_topography.id}`">
                            <img class="img-thumbnail mw-100"
                                 :src="_topography.thumbnail">
                        </a>
                    </div>
                    <div class="col-10">
                        <div class="container">
                            <div class="row">
                                <div class="col-6">
                                    <label for="input-name">Name</label>
                                    <b-form-input id="input-name"
                                                  v-model="_topography.name"
                                                  :disabled="!_editing">
                                    </b-form-input>
                                </div>
                                <div class="col-3">
                                    <label for="input-measurement-date">Date</label>
                                    <b-form-input id="input-measurement-date"
                                                  type="date"
                                                  v-model="_topography.measurement_date"
                                                  :disabled="!_editing">
                                    </b-form-input>
                                </div>
                                <div class="col-3">
                                    <label for="input-periodic">Flags</label>
                                    <b-form-checkbox id="input-periodic"
                                                     v-model="_topography.is_periodic"
                                                     :disabled="!_editing">
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
                                                      :class="{ 'border-danger': _topography.size_x === null }"
                                                      v-model="_topography.size_x"
                                                      :disabled="!_editing || !_topography.size_editable">
                                        </b-form-input>
                                        <span v-if="_topography.resolution_y !== null"
                                              class="input-group-text">
                                            &times;
                                        </span>
                                        <b-form-input v-if="_topography.resolution_y !== null"
                                                      type="number"
                                                      step="any"
                                                      :class="{ 'border-danger': _topography.size_y === null }"
                                                      v-model="_topography.size_y"
                                                      :disabled="!_editing || !_topography.size_editable">
                                        </b-form-input>
                                        <b-form-select class="unit-select"
                                                       :options="_units"
                                                       v-model="_topography.unit"
                                                       :class="{ 'border-danger': _topography.unit === null }"
                                                       :disabled="!_editing || !_topography.unit_editable">
                                        </b-form-select>
                                    </div>
                                </div>
                                <div class="col-4">
                                    <label for="input-physical-size">Height scale</label>
                                    <b-form-input id="input-physical-size"
                                                  type="number"
                                                  step="any"
                                                  :class="{ 'border-danger': _topography.height_scale === null }"
                                                  v-model="_topography.height_scale"
                                                  :disabled="!_editing || !_topography.height_scale_editable">
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
                                                     v-model="_topography.description"
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
                                                 v-model="_topography.tags"
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
                                                  v-model="_topography.instrument_name"
                                                  :disabled="!_editing">
                                    </b-form-input>
                                </div>
                                <div class="col-6">
                                    <label for="input-instrument-type">Instrument type</label>
                                    <b-form-select id="input-instrument-type"
                                                   :options="_instrumentChoices"
                                                   v-model="_topography.instrument_type"
                                                   :disabled="!_editing">
                                    </b-form-select>
                                </div>
                            </div>
                            <div v-if="_topography.instrument_type == 'microscope-based'" class="row">
                                <div class="col-12 mt-1">
                                    <label for="input-instrument-resolution">Instrument resolution</label>
                                    <div id="input-instrument-resolution" class="input-group mb-1">
                                        <b-form-input type="number"
                                                      step="any"
                                                      :placeholder="defaultResolutionValue"
                                                      v-model="_instrument_parameters_resolution_value"
                                                      :disabled="!_editing">
                                        </b-form-input>
                                        <b-form-select style="width: 100px;"
                                                       :options="_units"
                                                       :placeholder="defaultResolutionUnit"
                                                       v-model="_instrument_parameters_resolution_unit"
                                                       :disabled="!_editing">
                                        </b-form-select>
                                    </div>
                                </div>
                            </div>
                            <div v-if="_topography.instrument_type == 'contact-based'" class="row">
                                <div class="col-12 mt-1">
                                    <label for="input-instrument-tip-radius">Probe tip radius</label>
                                    <div id="input-instrument-tip-radius" class="input-group mb-1">
                                        <b-form-input type="number"
                                                      step="any"
                                                      :placeholder="defaultTipRadiusValue"
                                                      v-model="_instrument_parameters_tip_radius_value"
                                                      :disabled="!_editing">
                                        </b-form-input>
                                        <b-form-select style="width: 100px;"
                                                       :options="_units"
                                                       :placeholder="defaultTipRadiusUnit"
                                                       v-model="_instrument_parameters_tip_radius_unit"
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
                                                       v-model="_topography.detrend_mode"
                                                       :disabled="!_editing">
                                        </b-form-select>
                                    </div>
                                </div>
                                <div class="col-6 mt-1">
                                    <label for="input-undefined-data">Undefined/missing data</label>
                                    <div id="input-undefined-data" class="input-group mb-1">
                                        <b-form-select :options="_undefinedDataChoices"
                                                       v-model="_topography.fill_undefined_data_mode"
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
        <div v-if="!enlarged"
             class="card-footer">
            <topography-badges :topography="_topography"></topography-badges>
        </div>
    </div>
    <b-modal v-if="_topography !== null"
             v-model="_showDeleteModal"
             @ok="deleteTopography"
             title="Delete measurement">
        You are about to delete the measurement with name <b>{{ _topography.name }}</b>.
        Are you sure you want to proceed?
    </b-modal>
</template>

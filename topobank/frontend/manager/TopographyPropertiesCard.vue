<script>

import axios from "axios";

import {
    BAlert, BFormCheckbox, BFormInput, BFormSelect, BFormTags, BFormTextarea, BSpinner
} from 'bootstrap-vue-next';

import {formatExponential} from "../utils/formatting";

export default {
    name: 'topography-properties-card',
    components: {
        BAlert,
        BFormCheckbox,
        BFormInput,
        BFormSelect,
        BFormTags,
        BFormTextarea,
        BSpinner
    },
    emits: [
        'topography-deleted',
        'topography-updated'
    ],
    props: {
        data: {
            type: Object,
            default: null
        },
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
        enlarged: {
            type: Boolean,
            default: false
        },
        topographyUrl: {
            type: String,
            default: null
        }
    },
    data() {
        return {
            _data: null,
            _descriptionVisible: this.enlarged,
            _editing: false,
            _error: null,
            _filtersVisible: this.enlarged,
            _instrument_parameters_resolution_value: null,
            _instrument_parameters_resolution_unit: null,
            _instrument_parameters_tip_radius_value: null,
            _instrument_parameters_tip_radius_unit: null,
            _instrumentVisible: this.enlarged,
            _saving: false,
            _topographyUrl: this.topographyUrl === null ? this.data.url : this.topographyUrl,
            _savedData: null,
            _units: [
                {value: "km", text: 'km'},
                {value: "m", text: 'm'},
                {value: "mm", text: 'mm'},
                {value: "µm", text: 'µm'},
                {value: "nm", text: 'nm'},
                {value: "Å", text: 'Å'},
                {value: "pm", text: 'pm'}
            ],
            _instrumentChoices: [
                {value: 'undefined', text: 'Instrument of unknown type - all data considered as reliable'},
                {value: 'microscope-based', text: 'Microscope-based instrument with known resolution'},
                {value: 'contact-based', text: 'Contact-based instrument with known tip radius'}
            ],
            _detrendChoices: [
                {value: 'center', text: 'No detrending, but subtract mean height'},
                {value: 'height', text: 'Remove tilt'},
                {value: 'curvature', text: 'Remove curvature and tilt'}
            ],
            _undefinedDataChoices: [
                {value: 'do-not-fill', text: 'Do not fill undefined data points'},
                {value: 'harmonic', text: 'Interpolate undefined data points with harmonic functions'}
            ]
        }
    },
    mounted() {
        if (this.data !== null) {
            this.mogrifyDataFromGETRequest(this.data);
        } else {
            this.updateCard();
        }
    },
    methods: {
        updateCard() {
            /* Fetch JSON describing the card */
            axios.get(this._topographyUrl).then(response => {
                this._data = response.data;
                this._topographyUrl = response.data.url;
            });
        },
        mogrifyDataFromGETRequest(data) {
            // Get data object
            this._data = data;
            this._topographyUrl = data.url;

            // Flatten instrument parameters
            if (data.instrument_parameters.resolution !== undefined) {
                this._instrument_parameters_resolution_value = data.instrument_parameters.resolution.value;
                this._instrument_parameters_resolution_unit = data.instrument_parameters.resolution.unit;
            } else {
                this._instrument_parameters_resolution_value = this.defaultResolutionValue;
                this._instrument_parameters_resolution_unit = this.defaultResolutionUnit;
            }

            if (data.instrument_parameters.tip_radius !== undefined) {
                this._instrument_parameters_tip_radius_value = data.instrument_parameters.tip_radius.value;
                this._instrument_parameters_tip_radius_unit = data.instrument_parameters.tip_radius.unit;
            } else {
                this._instrument_parameters_tip_radius_value = this.defaultTipRadiusValue;
                this._instrument_parameters_tip_radius_unit = this.defaultTipRadiusUnit;
            }
        },
        mogrifyDataForPATCHRequest() {
            // Copy writable entries
            let writeableEntries = [
                'description', 'instrument_name', 'instrument_parameters', 'instrument_type', 'is_periodic',
                'measurement_date', 'name', 'tags', 'detrend_mode', 'fill_undefined_data_mode', 'data_source'
            ];
            if (this._data.size_editable) {
                writeableEntries.push('size_x', 'size_y');
            }
            if (this._data.unit_editable) {
                writeableEntries.push('unit');
            }
            if (this._data.height_scale_editable) {
                writeableEntries.push('height_scale');
            }

            let returnDict = {};
            for (const e of writeableEntries) {
                returnDict[e] = this._data[e];
            }

            // Unflatten instrument parameters
            returnDict.instrument_parameters = {
                resolution: {
                    value: this._instrument_parameters_resolution_value,
                    unit: this._instrument_parameters_resolution_unit
                },
                tip_radius: {
                    value: this._instrument_parameters_tip_radius_value,
                    unit: this._instrument_parameters_tip_radius_unit
                },
            }

            // Uncomment to simulate error on PATCH
            // returnDict['thumbnail'] = 'def';

            return returnDict;
        },
        saveCard() {
            this._editing = false;
            this._saving = true;
            axios.patch(this._topographyUrl, this.mogrifyDataForPATCHRequest()).then(response => {
                this._error = null;
                this.$emit('topography-updated', response.data);
                this.mogrifyDataFromGETRequest(response.data);
            }).catch(error => {
                this._error = error;
                this._data = this._savedData;
            }).finally(() => {
                this._saving = false;
            });
        },
        deleteTopography() {
            axios.delete(this._topographyUrl);
            this.$emit('topography-deleted', this._topographyUrl);
        }
    },
    watch: {
        data(newValue, oldValue) {
            this.mogrifyDataFromGETRequest(newValue);
        }
    },
    computed: {
        isMetadataIncomplete() {
            if (this._data !== null && this._data.is_metadata_complete !== undefined) {
                return !this._data.is_metadata_complete;
            } else {
                return true;
            }
        },
        channelOptions() {
            if (this._data === null) {
                return [];
            }

            let options = [];
            for (const [channelIndex, channelName] of this._data.channel_names.entries()) {
                options.push({value: channelIndex, text: channelName});
            }
            return options;
        },
        shortReliabilityCutoff() {
            return formatExponential(this._data.short_reliability_cutoff, 2) + ` m`;
        }
    }
};
</script>

<template>
    <div class="card mb-1" :class="{ 'bg-danger-subtle': isMetadataIncomplete }">
        <div class="card-header">
            <div v-if="_data !== null"
                 class="input-group-sm float-start">
                <b-form-select :options="channelOptions"
                               v-model="_data.data_source"
                               :disabled="!_editing">
                </b-form-select>
            </div>
            <div v-if="this._data !== null && !_editing && !_saving && !enlarged"
                 class="btn-group btn-group-sm float-end">
                <a class="btn btn-outline-secondary float-end ms-2"
                   :href="`/manager/html/topography/?topography=${this._data.id}`">
                    <i class="fa fa-expand"></i>
                </a>
            </div>
            <div v-if="!_editing && !_saving"
                 class="btn-group btn-group-sm float-end">
                <button class="btn btn-outline-secondary"
                        @click="_savedData = JSON.parse(JSON.stringify(_data)); _editing = true">
                    <i class="fa fa-pen"></i>
                </button>
                <button class="btn btn-outline-secondary"
                        @click="deleteTopography">
                    <i class="fa fa-trash"></i>
                </button>
            </div>
            <div v-if="_editing || _saving"
                 class="btn-group btn-group-sm float-end">
                <button v-if="_editing"
                        class="btn btn-danger"
                        @click="_editing = false; _data = _savedData">
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
            <b-alert :model-value="_error !== null"
                     variant="danger">
                {{ _error }}
            </b-alert>
            <div v-if="_data === null"
                 class="tab-content">
                <b-spinner small></b-spinner>
                Please wait...
            </div>
            <div v-if="_data !== null"
                 class="container">
                <div class="row">
                    <div class="col-2">
                        <img class="img-thumbnail mw-100"
                             :src="_data.thumbnail">
                    </div>
                    <div class="col-10">
                        <div class="container">
                            <div class="row">
                                <div class="col-6">
                                    <label for="input-name">Name</label>
                                    <b-form-input id="input-name"
                                                  v-model="_data.name"
                                                  :disabled="!_editing">
                                    </b-form-input>
                                </div>
                                <div class="col-3">
                                    <label for="input-measurement-date">Date</label>
                                    <b-form-input id="input-measurement-date"
                                                  type="date"
                                                  v-model="_data.measurement_date"
                                                  :disabled="!_editing">
                                    </b-form-input>
                                </div>
                                <div class="col-3">
                                    <label for="input-periodic">Flags</label>
                                    <b-form-checkbox id="input-periodic"
                                                     v-model="_data.is_periodic"
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
                                                      :class="{ 'border-danger': _data.size_x === null }"
                                                      v-model="_data.size_x"
                                                      :disabled="!_editing || !_data.size_editable">
                                        </b-form-input>
                                        <span v-if="_data.resolution_y !== null"
                                              class="input-group-text">
                                            &times;
                                        </span>
                                        <b-form-input v-if="_data.resolution_y !== null"
                                                      type="number"
                                                      step="any"
                                                      :class="{ 'border-danger': _data.size_y === null }"
                                                      v-model="_data.size_y"
                                                      :disabled="!_editing || !_data.size_editable">
                                        </b-form-input>
                                        <b-form-select class="unit-select"
                                                       :options="_units"
                                                       v-model="_data.unit"
                                                       :class="{ 'border-danger': _data.unit === null }"
                                                       :disabled="!_editing || !_data.unit_editable">
                                        </b-form-select>
                                    </div>
                                </div>
                                <div class="col-4">
                                    <label for="input-physical-size">Height scale</label>
                                    <b-form-input id="input-physical-size"
                                                  type="number"
                                                  step="any"
                                                  :class="{ 'border-danger': _data.height_scale === null }"
                                                  v-model="_data.height_scale"
                                                  :disabled="!_editing || !_data.height_scale_editable">
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
                                                     v-model="_data.description"
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
                                                 v-model="_data.tags"
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
                                                  v-model="_data.instrument_name"
                                                  :disabled="!_editing">
                                    </b-form-input>
                                </div>
                                <div class="col-6">
                                    <label for="input-instrument-type">Instrument type</label>
                                    <b-form-select id="input-instrument-type"
                                                   :options="_instrumentChoices"
                                                   v-model="_data.instrument_type"
                                                   :disabled="!_editing">
                                    </b-form-select>
                                </div>
                            </div>
                            <div v-if="_data.instrument_type == 'microscope-based'" class="row">
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
                            <div v-if="_data.instrument_type == 'contact-based'" class="row">
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
                                                       v-model="_data.detrend_mode"
                                                       :disabled="!_editing">
                                        </b-form-select>
                                    </div>
                                </div>
                                <div class="col-6 mt-1">
                                    <label for="input-undefined-data">Undefined/missing data</label>
                                    <div id="input-undefined-data" class="input-group mb-1">
                                        <b-form-select :options="_undefinedDataChoices"
                                                       v-model="_data.fill_undefined_data_mode"
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
        <div class="card-footer">
            <div v-if="_data !== null && _data.resolution_y !== null">
                <span class="badge bg-warning ms-1">{{ _data.datafile_format }}</span>
                <span class="badge bg-info ms-2">{{ _data.resolution_x }} &times; {{
                        _data.resolution_y
                    }} data points</span>
                <span v-if="_data.has_undefined_data" class="badge bg-danger ms-2">undefined data</span>
                <span v-if="isMetadataIncomplete" class="badge bg-danger ms-2">metadata incomplete</span>
                <span v-if="_data.short_reliability_cutoff !== null" class="badge bg-dark ms-2">
                    reliability cutoff {{ shortReliabilityCutoff }}
                </span>
            </div>
            <div v-if="_data !== null && _data.resolution_y === null">
                <div class="badge bg-warning ms-1">{{ _data.datafile_format }}</div>
                <div class="badge bg-info ms-2">{{ _data.resolution_x }} data points</div>
                <span v-if="_data.has_undefined_data" class="badge bg-danger ms-2">undefined data</span>
                <span v-if="isMetadataIncomplete" class="badge bg-danger ms-2">metadata incomplete</span>
                <span v-if="_data.short_reliability_cutoff !== null" class="badge bg-dark ms-2">
                    reliability cutoff {{ shortReliabilityCutoff }}
                </span>
            </div>
        </div>
    </div>
</template>

<script>

import { v4 as uuid4 } from 'uuid';

import {
    BAlert, BFormCheckbox, BFormInput, BFormSelect, BFormTags, BFormTextarea, BSpinner
} from 'bootstrap-vue-next';


function jsonOrError(response) {
    if (!response.ok) {
        throw Error(response.statusText);
    }
    return response.json();
}


export default {
    name: 'topography-properties-card',
    inject: ['csrfToken'],
    components: {
        BAlert,
        BFormCheckbox,
        BFormInput,
        BFormSelect,
        BFormTags,
        BFormTextarea,
        BSpinner
    },
    props: {
        apiUrl: {
            type: String,
            default: '/manager/api/topography'
        },
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
        topographyId: {
            type: Number,
            default: null
        },
        uid: {
            type: String,
            default() {
                return uuid4();
            }
        }
    },
    data() {
        return {
            _data: null,
            _descriptionVisible: false,
            _editing: false,
            _error: null,
            _filtersVisible: false,
            _instrument_parameters_resolution_value: null,
            _instrument_parameters_resolution_unit: null,
            _instrument_parameters_tip_radius_value: null,
            _instrument_parameters_tip_radius_unit: null,
            _instrumentVisible: false,
            _saving: false,
            _topographyId: this.topographyId === null ? this.data.id : this.topographyId,
            _savedData: null,
            _units: [
                { value: "km", text: 'km' },
                { value: "m", text: 'm' },
                { value: "mm", text: 'mm' },
                { value: "µm", text: 'µm' },
                { value: "nm", text: 'nm' },
                { value: "Å", text: 'Å' },
                { value: "pm", text: 'pm' }
            ],
            _instrumentTypes: [
                { value: 'undefined', text: 'Instrument of unknown type - all data considered as reliable' },
                { value: 'microscope-based', text: 'Microscope-based instrument with known resolution' },
                { value: 'contact-based', text: 'Contact-based instrument with known tip radius' }
            ]
        }
    },
    mounted() {
        if (this.data !== null) {
            this.mogrifyDataFromGETRequest(this.data);
            console.log(this._data);
            this.updateCard();
        }
    },
    methods: {
        updateCard() {
            /* Fetch JSON describing the card */
            fetch(`${this.apiUrl}/${this._topographyId}/`, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                    'X-CSRFToken': this.csrfToken
                }
            })
                .then(response => response.json())
                .then(data => {
                    this._data = data;
                    this._topographyId = data.id;
                });
        },
        mogrifyDataFromGETRequest(data) {
            // Get data object
            this._data = data;
            this._topographyId = data.id;

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
            let writableEntries = ['description', 'instrument_name', 'instrument_parameters', 'instrument_type', 'is_periodic', 'meansurement_data', 'name', 'tags'];
            if (this._data.size_editable) {
                writableEntries.push('size_x', 'size_y');
            }
            if (this._data.unit_editable) {
                writeableEntries.push('unit');
            }

            let returnDict = {};
            for (const e of writableEntries) {
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
            fetch(`${this.apiUrl}/${this._topographyId}/`, {
                method: 'PATCH',
                body: JSON.stringify(this.mogrifyDataForPATCHRequest()),
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                }
            })
                .then(jsonOrError)
                .then(data => {
                    this._error = null;
                    this.mogrifyDataFromGETRequest(data);
                })
                .catch(error => {
                    this._error = error;
                    this._data = this._savedData;
                })
                .finally(() => {
                    this._saving = false;
                });
        }
    }
};
</script>

<template>
    <div class="card mb-1">
        <div class="card-header">
            <div class="btn-group btn-group-sm float-end">
                <button v-if="!_editing && !_saving" class="btn btn-outline-secondary float-end"
                    @click="_savedData = JSON.parse(JSON.stringify(_data)); _editing = true">
                    Edit
                </button>
                <button v-if="_editing" class="btn btn-danger float-end" @click="_editing = false; _data = _savedData">
                    Discard
                </button>
                <button v-if="_editing || _saving" class="btn btn-success float-end" @click="saveCard">
                    <b-spinner small v-if="_saving"></b-spinner>
                    SAVE
                </button>
            </div>
            <div class="btn-group btn-group-sm float-end me-5">
                <button class="btn btn-outline-secondary" :class="{ active: _descriptionVisible }"
                    @click="_descriptionVisible = !_descriptionVisible">
                    Description
                </button>
                <button class="btn btn-outline-secondary" :class="{ active: _instrumentVisible }"
                    @click="_instrumentVisible = !_instrumentVisible">
                    Instrument
                </button>
                <button class="btn btn-outline-secondary" :class="{ active: _filtersVisible }"
                    @click="_filtersVisible = !_filtersVisible">
                    Filters
                </button>
            </div>
            <div v-if="_data !== null && _data.resolution_y !== null">
                <h5 class="d-inline">Topography map</h5>
                <span class="badge bg-info ms-2">{{ _data.resolution_x }} &times; {{
                    _data.resolution_y
                }} data points</span>
                <span class="badge bg-warning ms-1">{{ _data.datafile_format }}</span>
            </div>
            <div v-if="_data !== null && _data.resolution_y === null">
                <h5 class="d-inline">Line scan</h5>
                <div class="badge bg-info ms-2">{{ _data.resolution_x }} data points</div>
                <div class="badge bg-warning ms-1">{{ _data.datafile_format }}</div>
            </div>
        </div>
        <div class="card-body">
            <b-alert :model-value="_error !== null"
                     variant="danger">
                {{ _error }}
            </b-alert>
            <div v-if="_data === null" class="tab-content">
                <b-spinner small></b-spinner> Please wait...
            </div>
            <div v-if="_data !== null">
                <div class="row">
                    <div class="col-2">
                        <img class="img-thumbnail" :src="_data.thumbnail">
                    </div>
                    <div class="col-10">
                        <div class="row">
                            <div class="col-4">
                                <label for="input-name">Name</label>
                                <b-form-input id="input-name" v-model="_data.name" :disabled="!_editing">
                                </b-form-input>
                            </div>
                            <div class="col-4">
                                <label for="input-physical-size">Physical size</label>
                                <div class="input-group mb-1">
                                    <input id="input-physical-size" type="number" step="any" class="form-control"
                                        v-model="_data.size_x" :disabled="!_editing || !_data.size_editable">
                                    <span class="input-group-text">&times;</span>
                                    <input type="number" step="any" class="form-control" v-model="_data.size_y"
                                        :disabled="!_editing || !_data.size_editable">
                                    <b-form-select :options="_units" v-model="_data.unit"
                                        :disabled="!_editing || !_data.unit_editable">
                                    </b-form-select>
                                </div>
                            </div>
                            <div class="col-2">
                                <label for="input-physical-size">Height scale</label>
                                <b-form-input id="input-physical-size" type="number" step="any" v-model="_data.height_scale"
                                    :disabled="!_editing || !_data.height_scale_editable">
                                </b-form-input>
                            </div>
                            <div class="col-2">
                                <label for="input-measurement-date">Date</label>
                                <b-form-input id="input-measurement-date" type="date" v-model="_data.measurement_date"
                                    :disabled="!_editing">
                                </b-form-input>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-12">
                                <b-form-checkbox v-model="_data.is_periodic" :disabled="!_editing">
                                    This topography should be considered periodic in terms of a repeating array of
                                    the uploaded data
                                </b-form-checkbox>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-12">
                                <label for="input-tags">Tags</label>
                                <b-form-tags id="input-tags" v-model="_data.tags" :disabled="!_editing">
                                </b-form-tags>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="row mt-2">
                    <div class="col-12">
                        <div class="row" v-if="_descriptionVisible">
                            <div class="col-12">
                                <b-form-textarea placeholder="Please provide a short description of this measurement"
                                                 v-model="_data.description"
                                                 :disabled="!_editing"
                                                 rows="5">
                                </b-form-textarea>
                            </div>
                        </div>
                        <div v-if="_instrumentVisible">
                            <div class="row">
                                <div class="col-6">
                                    <label for="input-instrument-name">Instrument name</label>
                                    <b-form-input id="input-instrument-name" v-model="_data.instrument_name"
                                        :disabled="!_editing">
                                    </b-form-input>
                                </div>
                                <div class="col-6">
                                    <label for="input-instrument-type">Instrument type</label>
                                    <b-form-select id="input-instrument-type" :options="_instrumentTypes"
                                        v-model="_data.instrument_type" :disabled="!_editing">
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
                        <div class="row" v-if="_filtersVisible">
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script>

import {v4 as uuid4} from 'uuid';

import {
    BAccordion, BAccordionItem, BFormCheckbox, BFormInput, BFormSelect, BFormTags,
    BFormTextarea
} from 'bootstrap-vue-next';

export default {
    name: 'topography-properties-card',
    inject: ['csrfToken'],
    components: {
        BAccordion,
        BAccordionItem,
        BFormCheckbox,
        BFormInput,
        BFormSelect,
        BFormTags,
        BFormTextarea
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
            _data: this.data,
            _editing: false,
            _topographyId: this.topographyId === null ? this.data.id : this.topographyId,
            _units: [
                {value: "km", text: 'km'},
                {value: "m", text: 'm'},
                {value: "mm", text: 'mm'},
                {value: "µm", text: 'µm'},
                {value: "nm", text: 'nm'},
                {value: "Å", text: 'Å'},
                {value: "pm", text: 'pm'}
            ],
            _instrumentTypes: [
                {value: 'undefined', text: 'Instrument of unknown type - all data considered as reliable'},
                {value: 'microscope-based', text: 'Microscope-based instrument with known resolution'},
                {value: 'contact-based', text: 'Contact-based instrument with known tip radius'}
            ]
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
            fetch(`${this.apiUrl}/${this.topographyId}/`, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                    'X-CSRFToken': this.csrfToken
                }
            })
                .then(response => response.json())
                .then(data => {
                    this._data = data;
                    console.log(data);
                });
        }
    }
};
</script>

<template>
    <div class="card mb-1">
        <div class="card-header">
            <div class="btn-group btn-group-sm float-end">
                <button v-if="!_editing"
                        class="btn btn-outline-secondary float-end ms-1"
                        @click="_editing=true">
                    Edit
                </button>
                <button v-if="_editing"
                        class="btn btn-danger float-end ms-1"
                        @click="_editing=false">
                    Discard
                </button>
                <button v-if="_editing"
                        class="btn btn-success float-end ms-1"
                        @click="_editing=false">
                    SAVE
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
            <div v-if="_data === null"
                 class="tab-content">
                <span class="spinner"></span>
                <div>Please wait...</div>
            </div>
            <div v-if="_data !== null">
                <div class="row">
                    <div class="col-2">
                        <img class="img-thumbnail"
                             :src="_data.thumbnail">
                    </div>
                    <div class="col-10">
                        <div class="row">
                            <div class="col-4">
                                <label for="input-name">Name</label>
                                <b-form-input id="input-name"
                                              v-model="_data.name"
                                              :disabled="!_editing">
                                </b-form-input>
                            </div>
                            <div class="col-4">
                                <label for="input-physical-size">Physical size</label>
                                <div class="input-group mb-1">
                                    <input id="input-physical-size"
                                           type="number"
                                           step="any"
                                           class="form-control"
                                           v-model="_data.size_x"
                                           :disabled="!_editing || !_data.size_editable">
                                    <span class="input-group-text">&times;</span>
                                    <input type="number"
                                           step="any"
                                           class="form-control"
                                           v-model="_data.size_y"
                                           :disabled="!_editing || !_data.size_editable">
                                    <b-form-select :options="_units"
                                                   v-model="_data.unit"
                                                   :disabled="!_editing || !_data.unit_editable">
                                    </b-form-select>
                                </div>
                            </div>
                            <div class="col-2">
                                <label for="input-physical-size">Height scale</label>
                                <b-form-input id="input-physical-size"
                                              type="number"
                                              step="any"
                                              v-model="_data.height_scale"
                                              :disabled="!_editing || !_data.height_scale_editable">
                                </b-form-input>
                            </div>
                            <div class="col-2">
                                <label for="input-measurement-date">Date</label>
                                <b-form-input id="input-measurement-date"
                                              type="date"
                                              v-model="_data.measurement_date"
                                              :disabled="!_editing">
                                </b-form-input>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-12">
                                <b-form-checkbox v-model="_data.is_periodic"
                                                 :disabled="!_editing">
                                    This topography should be considered periodic in terms of a repeating array of
                                    the uploaded data
                                </b-form-checkbox>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-12">
                                <label for="input-tags">Tags</label>
                                <b-form-tags id="input-tags"
                                             v-model="_data.tags"
                                             :disabled="!_editing">
                                </b-form-tags>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="row mt-2">
                    <div class="col-12">
                        <b-accordion>
                            <b-accordion-item title="Description">
                                <b-form-textarea placeholder="Please provide a short description of this measurement"
                                                 v-model="_data.description"
                                                 :disabled="!_editing">
                                </b-form-textarea>
                            </b-accordion-item>
                            <b-accordion-item title="Instrument">
                                <div class="row">
                                    <div class="col-6">
                                        <label for="input-instrument-name">Name</label>
                                        <b-form-input id="input-instrument-name"
                                                      v-model="_data.instrument_name"
                                                      :disabled="!_editing">
                                        </b-form-input>
                                    </div>
                                    <div class="col-6">
                                        <label for="input-instrument-type">Type</label>
                                        <b-form-select id="input-instrument-type"
                                                       :options="_instrumentTypes"
                                                       v-model="_data.instrument_type"
                                                       :disabled="!_editing">
                                        </b-form-select>
                                    </div>
                                </div>
                                <div v-if="_data.instrument_type == 'microscope-based'" class="row">
                                    <div class="col-12 mt-1">
                                        <label for="input-instrument-resolution">Resolution</label>
                                        <div id="input-instrument-resolution"
                                             class="input-group mb-1">
                                            <b-form-input type="number"
                                                          step="any"
                                                          v-model="_data.instrument_parameters.resolution.value"
                                                          :disabled="!_editing">
                                            </b-form-input>
                                            <b-form-select style="width: 100px;"
                                                           :options="_units"
                                                          v-model="_data.instrument_parameters.resolution.unit"
                                                           :disabled="!_editing">
                                            </b-form-select>
                                        </div>
                                    </div>
                                </div>
                                <div v-if="_data.instrument_type == 'contact-based'" class="row">
                                    <div class="col-12 mt-1">
                                        <label for="input-instrument-tip-radius">Tip radius</label>
                                        <div id="input-instrument-tip-radius"
                                             class="input-group mb-1">
                                            <b-form-input type="number"
                                                          step="any"
                                                          v-model="_data.instrument_parameters.tip_radius.value"
                                                          :disabled="!_editing">
                                            </b-form-input>
                                            <b-form-select style="width: 100px;"
                                                           :options="_units"
                                                           v-model="_data.instrument_parameters.tip_radius.unit"
                                                           :disabled="!_editing">
                                            </b-form-select>
                                        </div>
                                    </div>
                                </div>
                            </b-accordion-item>
                            <b-accordion-item title="Filters">
                            </b-accordion-item>
                        </b-accordion>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

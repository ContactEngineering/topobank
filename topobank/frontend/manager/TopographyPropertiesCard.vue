<script>

import {v4 as uuid4} from 'uuid';

export default {
    name: 'topography-properties-card',
    inject: ['csrfToken'],
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
            _topographyId: this.topographyId === null ? this.data.id : this.topographyId
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
                        class="btn btn-default float-end ms-1"
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
                <span class="badge bg-info ms-2">{{ _data.resolution_x }} &times; {{ _data.resolution_y }} data points</span>
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
                                <div class="input-group mb-1">
                                    <input id="input-name"
                                           type="text"
                                           class="form-control"
                                           v-model="_data.name"
                                           :disabled="!_editing">
                                </div>
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
                                    <div class="input-group-append input-group-prepend">
                                        <span class="input-group-text">&times;</span>
                                    </div>
                                    <input type="number"
                                           step="any"
                                           class="form-control"
                                           v-model="_data.size_y"
                                           :disabled="!_editing || !_data.size_editable">
                                    <select class="form-control"
                                            v-model="_data.unit"
                                            :disabled="!_editing || !_data.unit_editable">
                                        <!-- Choices need to match Topography.LENGTH_UNIT_CHOICES -->
                                        <option value="km">km</option>
                                        <option value="m">m</option>
                                        <option value="mm">mm</option>
                                        <option value="µm">µm</option>
                                        <option value="nm">nm</option>
                                        <option value="Å">Å</option>
                                        <option value="pm">pm</option>
                                    </select>
                                </div>
                            </div>
                            <div class="col-2">
                                <label for="input-physical-size">Height scale</label>
                                <div class="input-group mb-1">
                                    <input id="input-physical-size"
                                           type="number"
                                           step="any"
                                           class="form-control"
                                           v-model="_data.height_scale"
                                           :disabled="!_editing || !_data.height_scale_editable">
                                </div>
                            </div>
                            <div class="col-2">
                                <label for="input-measurement-date">Date</label>
                                <div class="input-group mb-1">
                                    <input id="input-measurement-date"
                                           type="date"
                                           class="form-control"
                                           v-model="_data.measurement_date"
                                           :disabled="!_editing">
                                </div>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-12">
                                <div class="custom-control custom-checkbox">
                                    <input id="input-is-periodic"
                                           type="checkbox"
                                           class="custom-control-input"
                                           v-mode="_data.is_periodic"
                                           :disabled="!_editing">
                                    <label for="input-is-periodic"
                                           class="custom-control-label">
                                        This topography should be considered periodic in terms of a repeating array of
                                        the
                                        uploaded data
                                    </label>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="row">
                    <div class="col-12">
                        <div class="accordion">
                            <div class="accordion-item"
                                 id="topography-accordion">
                                <p class="accordion-header"
                                    id="description-header">
                                    <button class="accordion-button"
                                            type="button"
                                            data-bs-toggle="collapse"
                                            data-bs-target="#description-collapse"
                                            aria-expanded="true"
                                            aria-controls="description-collapse">
                                        Description
                                    </button>
                                </p>
                                <div id="description-collapse"
                                     class="accordion-collapse collapse show"
                                     aria-labelledby="description-header"
                                     data-bs-parent="#topography-accordion">
                                    <div class="accordion-body">
                                        <div class="input-group">
                                            <textarea id="input-description"
                                                      placeholder="Please provide a short description of this measurement"
                                                      class="form-control"
                                                      v-model="_data.description"
                                                      :disabled="!_editing">
                                            </textarea>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

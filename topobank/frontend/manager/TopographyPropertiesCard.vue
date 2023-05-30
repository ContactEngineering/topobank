<script>

import {v4 as uuid4} from 'uuid';

import VueDatePicker from '@vuepic/vue-datepicker';
import '@vuepic/vue-datepicker/dist/main.css'

export default {
    name: 'topography-properties-card',
    components: {
        VueDatePicker
    },
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
            <div class="btn-group btn-group-sm float-right">
                <button v-if="!_editing"
                        class="btn btn-default float-right ml-1"
                        @click="_editing=true">
                    Edit
                </button>
                <button v-if="_editing"
                        class="btn btn-danger float-right ml-1"
                        @click="_editing=false">
                    Discard
                </button>
                <button v-if="_editing"
                        class="btn btn-success float-right ml-1"
                        @click="_editing=false">
                    SAVE
                </button>
            </div>
            <div v-if="_data !== null && _data.resolution_y !== null">
                <h5>Topography map</h5>
                <small>{{ _data.resolution_x }} x {{ _data.resolution_y }} pixels</small>
            </div>
            <div v-if="_data !== null && _data.resolution_y === null">
                <h5>Line scan</h5>
                <small>{{ _data.resolution_x }} data points</small>
            </div>
        </div>
        <div class="card-body">
            <div v-if="_data === null"
                 class="tab-content">
                <span class="spinner"></span>
                <div>Please wait...</div>
            </div>
            <div v-if="_data !== null">
                <label for="input-name">Name</label>
                <div class="input-group mb-1">
                    <input id="input-name"
                           type="text"
                           class="form-control"
                           v-model="_data.name"
                           :disabled="!_editing">
                </div>
                <label for="input-measurement-date">Measurement date</label>
                <div class="input-group mb-1">
                    <vue-date-picker id="measurement-date"
                                     v-model="_data.measurement_date"
                                     :enable-time-picker="false"
                                     :disabled="!_editing">
                    </vue-date-picker>
                </div>
                <div class="input-group mb-1">
                    <div class="input-group-prepend">
                        <span class="input-group-text">Description</span>
                    </div>
                    <input type="text"
                           class="form-control"
                           v-model="_data.description"
                           :disabled="!_editing">
                </div>
                <div class="input-group mb-1">
                    <div class="input-group-prepend">
                        <span class="input-group-text">Physical size</span>
                    </div>
                    <input type="text"
                           class="form-control"
                           v-model="_data.size_x"
                           :disabled="!_editing">
                    <div class="input-group-append">
                        <span class="input-group-text">x</span>
                    </div>
                    <input type="text"
                           class="form-control"
                           v-model="_data.size_y"
                           :disabled="!_editing">
                    <input type="text"
                           class="form-control"
                           v-model="_data.unit"
                           :disabled="!_editing">
                </div>
            </div>
        </div>
    </div>
</template>

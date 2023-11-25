<script>

import axios from "axios";

import {
    BSpinner
} from 'bootstrap-vue-next';

export default {
    name: 'topography-pending-card',
    components: {
        BSpinner
    },
    emits: [
        'delete:topography',
        'update:topography'
    ],
    props: {
        url: String,  // API url
        name: String,  // Used for the title of the card
        taskState: String  // State of task, 'pe', 'st', etc
    },
    methods: {
        deleteTopography() {
            axios.delete(this.url);
            this.$emit('delete:topography', this.url);
        },
        forceInspect() {
            axios.post(`${this.url}force-inspect/`).then(response => {
                this.$emit('update:topography', response.data);
            });
        }
    }
};
</script>

<template>
    <div class="card mb-1">
        <div class="card-header">
            <div class="btn-group btn-group-sm float-end">
                <button class="btn btn-outline-secondary">
                    <i class="fa fa-refresh"
                       @click="forceInspect"></i>
                </button>
                <button class="btn btn-outline-secondary float-end"
                        @click="deleteTopography">
                    <i class="fa fa-trash"></i>
                </button>
            </div>
            <div>
                <h5 class="d-inline">{{ name }}</h5>
            </div>
        </div>
        <div v-if="taskState !== 'st'"
             class="card-body">
            <b-spinner small  type="grow"></b-spinner>
            Waiting for data file inspection to start...
        </div>
        <div v-if="taskState === 'st'"
             class="card-body">
            <b-spinner small></b-spinner>
            Inspecting data file and applying filters...
        </div>
    </div>
</template>

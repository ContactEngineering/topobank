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
        'topography-deleted'
    ],
    props: {
        url: String,  // API url
        name: String,  // Used for the title of the card
    },
    methods: {
        deleteTopography() {
            axios.delete(this.url);
            this.$emit('topography-deleted', this.url);
        }
    }
};
</script>

<template>
    <div class="card text-white bg-secondary mb-1">
        <div class="card-header">
            <div class="btn-group btn-group-sm float-end">
                <button class="btn btn-outline-light text-white float-end"
                        @click="deleteTopography">
                    <i class="fa fa-trash"></i>
                </button>
            </div>
            <div>
                <h5 class="d-inline">{{ name }}</h5>
            </div>
        </div>
        <div class="card-body">
            <b-spinner small></b-spinner>
            Inspecting data file...
        </div>
    </div>
</template>

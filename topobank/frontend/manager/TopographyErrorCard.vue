<script>

import axios from "axios";

import {
    BProgress
} from 'bootstrap-vue-next';

export default {
    name: 'topography-error-card',
    components: {
        BProgress
    },
    emits: [
        'topography-deleted'
    ],
    props: {
        url: String,  // API url
        name: String,  // Used for the title of the card
        error: String,  // Error string to display
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
    <div class="card text-white bg-danger mb-1">
        <div class="card-header">
            <div class="btn-group btn-group-sm float-end">
                <button v-if="!_editing && !_saving" class="btn btn-outline-light text-white float-end"
                        @click="deleteTopography">
                    <i class="fa fa-trash"></i>
                </button>
            </div>
            <div>
                <h5 class="d-inline">{{ name }}</h5>
            </div>
        </div>
        <div class="card-body">
            {{ error }}
        </div>
    </div>
</template>

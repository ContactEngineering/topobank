<script>

import axios from "axios";

import {
    BProgress
} from 'bootstrap-vue-next';

export default {
    name: 'topography-upload-card',
    components: {
        BProgress
    },
    emits: [
        'upload-successful'
    ],
    props: {
        name: String,  // Used for the title of the card
        file: Object,  // File object containing the actual data
        postData: Object,  // Target URL
    },
    data() {
        return {
            _loaded: 0,
            _total: 1
        }
    },
    mounted() {
        // Start upload
        axios.postForm(
            this.postData.url,
            {...this.postData.fields, file: this.file},
            {onUploadProgress: this.onProgress}
        ).then(response => {
            // Upload successfully finished
            this.$emit('upload-successful', this.postData.url);
        });
    },
    methods: {
        onProgress(e) {
            this._loaded = e.loaded;
            this._total = e.total;
        }
    }
};
</script>

<template>
    <div class="card mb-1">
        <div class="card-header">
            <div>
                <h5 class="d-inline">{{ name }}</h5>
            </div>
        </div>
        <div class="card-body">
            <b-progress show-progress animated
                        :value="_loaded"
                        :max="_total">
            </b-progress>
        </div>
    </div>
</template>

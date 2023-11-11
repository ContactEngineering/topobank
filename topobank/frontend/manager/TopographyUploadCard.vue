<script>

import axios from "axios";

import {
    BProgress
} from 'bootstrap-vue-next';
import {concat} from "lodash";

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
        uploadInstructions: Object,  // Target URL
    },
    data() {
        return {
            _loaded: 0,
            _total: 1
        }
    },
    mounted() {
        console.log(this.uploadInstructions);
        // Start upload
        if (this.uploadInstructions.method === 'POST') {
            axios.postForm(
                this.uploadInstructions.url,
                {...this.uploadInstructions.fields, file: this.file},
                {onUploadProgress: this.onProgress}
            ).then(response => {
                // Upload successfully finished
                this.$emit('upload-successful', this.uploadInstructions.url);
            });
        } else if (this.uploadInstructions.method === 'PUT') {
            /*
            axios.request({
                method: 'put',
                url: this.uploadInstructions.url,
                data: this.file,
                onUploadProgress: this.onProgress
            }).then(response => {
                // Upload successfully finished
                this.$emit('upload-successful', this.uploadInstructions.url);
            });
             */

                /*
            fetch(this.uploadInstructions.url, {
                method: 'PUT',
                body: this.file
            }).then(response => {
                // Upload successfully finished
                this.$emit('upload-successful', this.uploadInstructions.url);
            });
                 */

            axios.put(
                this.uploadInstructions.url,
                this.file,
                {
                    headers: { 'Content-Type': 'binary/octet-stream' },
                    onUploadProgress: this.onProgress
                }
            ).then(response => {
                // Upload successfully finished
                this.$emit('upload-successful', this.uploadInstructions.url);
            });
        } else {
            alert(`Unknown upload method: "${this.uploadInstructions.method}`);
        }
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

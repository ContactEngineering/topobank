<script setup>

import axios from "axios";
import {onMounted, ref} from "vue";

import {
    BProgress
} from 'bootstrap-vue-next';

const emit = defineEmits([
    'upload-successful'
]);

const props = defineProps({
    name: String,  // Used for the title of the card
    file: Object,  // File object containing the actual data
    uploadInstructions: Object  // Target URL
});

const _loaded = ref(0);
const _total = ref(1);

function onProgress(e) {
    _loaded.value = e.loaded;
    _total.value = e.total;
}

onMounted(() => {
    // Start upload
    if (props.uploadInstructions.method === 'POST') {
        axios.postForm(
            props.uploadInstructions.url,
            {...props.uploadInstructions.fields, file: props.file},
            {onUploadProgress: onProgress}
        ).then(response => {
            // Upload successfully finished
            emit('upload-successful', props.uploadInstructions.url);
        });
    } else if (props.uploadInstructions.method === 'PUT') {
        axios.put(
            props.uploadInstructions.url,
            props.file,
            {
                headers: {'Content-Type': 'binary/octet-stream'},
                onUploadProgress: onProgress
            }
        ).then(response => {
            // Upload successfully finished
            emit('upload-successful', props.uploadInstructions.url);
        });
    } else {
        alert(`Unknown upload method: "${props.uploadInstructions.method}`);
    }
});

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

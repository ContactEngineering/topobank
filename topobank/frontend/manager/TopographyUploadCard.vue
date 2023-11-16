<script setup>

import axios from "axios";
import {cloneDeep} from "lodash";
import {onMounted, ref} from "vue";

import {
    BProgress
} from 'bootstrap-vue-next';

const emit = defineEmits([
    'update:topography'
]);

const props = defineProps({
    topography: Object
});

const _loaded = ref(0);
const _total = ref(1);

function onProgress(e) {
    _loaded.value = e.loaded;
    _total.value = e.total;
}

function emitUpdateTopography() {
    let t = cloneDeep(props.topography);
    // Remove upload instructions
    delete t.file;
    delete t.upload_instructions;
    // Notify that topography has changed
    emit('update:topography', t);
}

onMounted(() => {
    // Start upload
    if (props.topography.upload_instructions.method === 'POST') {
        axios.postForm(
            props.topography.upload_instructions.url,
            {...props.topography.upload_instructions.fields, file: props.topography.file},
            {onUploadProgress: onProgress}
        ).then(response => {
            // Upload successfully finished
            emitUpdateTopography();
        });
    } else if (props.topography.upload_instructions.method === 'PUT') {
        axios.put(
            props.topography.upload_instructions.url,
            props.topography.file,
            {
                headers: {'Content-Type': 'binary/octet-stream'},
                onUploadProgress: onProgress
            }
        ).then(response => {
            // Upload successfully finished
            emitUpdateTopography();
            a
        });
    } else {
        alert(`Unknown upload method: "${props.topography.upload_instructions.method}`);
    }
});

</script>

<template>
    <div class="card mb-1">
        <div class="card-header">
            <div>
                <h5 class="d-inline">{{ topography.name }}</h5>
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

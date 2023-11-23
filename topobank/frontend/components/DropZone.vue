<script setup>
/*
 * Inspired by https://www.smashingmagazine.com/2022/03/drag-drop-file-uploader-vuejs-3/
 */

import {onMounted, onUnmounted, ref} from "vue";

const emit = defineEmits([
    'files-dropped'
]);

const _events = ['dragenter', 'dragover', 'dragleave', 'drop'];

const _active = ref(false);

onMounted(() => {
    _events.forEach((eventName) => {
        document.body.addEventListener(eventName, preventDefaults);
    });
});

onUnmounted(() => {
    _events.forEach((eventName) => {
        document.body.removeEventListener(eventName, preventDefaults);
    })
});

function preventDefaults(e) {
    e.preventDefault();
}

function onDrop(e) {
    _active.value = false;
    emit('files-dropped', [...e.dataTransfer.files]);
}

function onSelect(e) {
    emit('files-dropped', e.target.files);
}

</script>

<template>
    <div class="drop-zone mb-1 bg-light"
         :class="{ 'drop-zone-active': _active }"
         :data-active="_active"
         @dragenter.prevent="_active=true"
         @dragover.prevent="_active=true"
         @dragleave.prevent="_active=false"
         @drop.prevent="onDrop">
        <!-- share state with the scoped slot -->
        <slot :dropZoneActive="_active">Drop your measurements here or </slot>
        <label>
            <span class="btn btn-primary">click to select files</span>
            <input class="d-none"
                   type="file"
                   multiple
                   @change="onSelect"/>
        </label>
        for upload.
    </div>
</template>

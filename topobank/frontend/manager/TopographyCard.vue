<script setup>

import axios from "axios";
import {computed, onMounted, ref} from "vue";

import TopographyErrorCard from "./TopographyErrorCard.vue";
import TopographyPendingCard from "./TopographyPendingCard.vue";
import TopographyPropertiesCard from "./TopographyPropertiesCard.vue";
import TopographyUploadCard from "./TopographyUploadCard.vue";

const props = defineProps({
    disabled: {
        type: Boolean,
        default: false
    },
    enlarged: {
        type: Boolean,
        default: false
    },
    topography: {
        type: Object,
        default: null
    },
    pollingInterval: {
        type: Number,
        default: 1000  // milliseconds
    },
    topographyUrl: {
        type: String,
        default: null
    }
});

const emit = defineEmits([
    'delete:topography',
    'update:topography',
]);

const _topography = ref(props.topography);

onMounted(() => {
    scheduleStateCheck();
});

const isUploading = computed(() => {
    return _topography.value !== null &&
        _topography.value.upload_instructions !== undefined &&
        _topography.value.upload_instructions !== null;
});

function scheduleStateCheck() {
    if (_topography.value === null) {
        checkState();
    } else if (_topography.value.task_state === 'pe') {
        setTimeout(checkState, props.pollingInterval);
    }
}

function checkState() {
    const topographyUrl = _topography.value === null ? props.topographyUrl : _topography.value.url;
    axios.get(topographyUrl).then(response => {
        _topography.value = response.data;
        emit('update:topography', _topography.value);
        scheduleStateCheck();
    });
}

function uploadSuccessful() {
    checkState();
}

function topographyDeleted(url) {
    emit('delete:topography', url);
}

function topographyUpdated(topography) {
    _topography.value = topography;
    emit('update:topography', _topography.value);
    scheduleStateCheck();
}

</script>

<template>
    <topography-upload-card
        v-if="_topography !== null && isUploading"
        :name="_topography.name"
        :file="_topography.file"
        :upload-instructions="_topography.upload_instructions"
        @upload-successful="uploadSuccessful">
    </topography-upload-card>
    <topography-pending-card
        v-if="_topography !== null && !isUploading && _topography.task_state !== 'su' && _topography.task_state !== 'fa'"
        :url="_topography.url"
        :name="_topography.name"
        @delete:topography="topographyDeleted"
        @update:topography="topographyUpdated">
    </topography-pending-card>
    <topography-error-card
        v-if="_topography !== null && !isUploading && _topography.task_state === 'fa'"
        :topography="_topography"
        @delete:topography="topographyDeleted"
        @update:topography="topographyUpdated">
    </topography-error-card>
    <topography-properties-card
        v-if="_topography !== null && !isUploading && _topography.task_state === 'su'"
        :topography="_topography"
        :enlarged="enlarged"
        :disabled="disabled"
        @delete:topography="topographyDeleted"
        @update:topography="topographyUpdated">
    </topography-properties-card>
</template>

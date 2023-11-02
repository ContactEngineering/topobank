<script setup>

import axios from "axios";
import {cloneDeep} from "lodash";
import {computed, onMounted, ref, watch, watchEffect} from "vue";

import TopographyErrorCard from "./TopographyErrorCard.vue";
import TopographyPendingCard from "./TopographyPendingCard.vue";
import TopographyPropertiesCard from "./TopographyPropertiesCard.vue";
import TopographyUploadCard from "./TopographyUploadCard.vue";

const props = defineProps({
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

const _topography = ref(cloneDeep(props.topography));

onMounted(() => {
    scheduleStateCheck();
});

function scheduleStateCheck() {
    if (_topography.value === null) {
        checkState();
    } else if (_topography.value.task_state !== 'su' && _topography.value.task_state !== 'fa') {
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

function topographyDeleted(url) {
    emit('delete:topography', url);
}

function topographyUpdated(topography) {
    _topography.value = cloneDeep(topography);
    emit('update:topography', _topography.value);
    scheduleStateCheck();
}

const isUploading = computed(() => {
    return _topography.value !== null &&
        _topography.value.post_data !== undefined &&
        _topography.value.post_data !== null;
});

</script>

<template>
    <topography-upload-card
        v-if="_topography !== null && isUploading"
        :name="_topography.name"
        :file="_topography.file"
        :post-data="_topography.post_data"
        @upload-successful="checkState">
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
        @delete:topography="topographyDeleted"
        @update:topography="topographyUpdated">
    </topography-properties-card>
</template>

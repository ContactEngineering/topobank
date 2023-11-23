<script setup>

import axios from "axios";
import {computed, onMounted, ref, watch} from "vue";

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
    pollingInterval: {
        type: Number,
        default: 1000  // milliseconds
    },
    selectable: {
        type: Boolean,
        default: false
    },
    selected: {
        type: Boolean,
        default: false
    },
    topography: {
        type: Object,
        default: null
    },
    topographyUrl: {
        type: String,
        default: null
    }
});

const emit = defineEmits([
    'delete:topography',
    'update:topography',
    'update:selected'
]);

let _currentTimeout = null;

onMounted(() => {
    scheduleStateCheck(props.topography);
});

const isUploading = computed(() => {
    return props.topography !== null && props.topography.upload_instructions != null;
});

function scheduleStateCheck(topography) {
    if (topography === null) {
        checkState();
    } else if (topography.upload_instructions == null && ['no', 'pe', 'st'].includes(topography.task_state)) {
        if (_currentTimeout != null) {
            clearTimeout(_currentTimeout);
        }
        _currentTimeout = setTimeout(checkState, props.pollingInterval);
    }
}

function checkState() {
    axios.get(props.topographyUrl).then(response => {
        emit('update:topography', response.data);
        scheduleStateCheck(response.data);
    });
}

function topographyDeleted(url) {
    emit('delete:topography', url);
}

const topographyModel = computed({
    get() {
        scheduleStateCheck(props.topography);
        return props.topography;
    },
    set(value) {
        emit('update:topography', value);
        scheduleStateCheck(value);
    }
});

const selectedModel = computed({
    get() {
        return props.selected;
    },
    set(value) {
        emit('update:selected', value);
    }
});

</script>

<template>
    <topography-upload-card
        v-if="topography !== null && isUploading"
        v-model:topography="topographyModel">
    </topography-upload-card>
    <topography-pending-card
        v-if="topography !== null && !isUploading && topography.task_state !== 'su' && topography.task_state !== 'fa'"
        :url="topographyUrl"
        :name="topography.name"
        :task-state="topography.task_state"
        @delete:topography="topographyDeleted"
        v-model:topography="topographyModel">
    </topography-pending-card>
    <topography-error-card
        v-if="topography !== null && !isUploading && topography.task_state === 'fa'"
        :topography-url="topographyUrl"
        :topography="topography"
        @delete:topography="topographyDeleted"
        v-model:topography="topographyModel">
    </topography-error-card>
    <topography-properties-card
        v-if="topography !== null && !isUploading && topography.task_state === 'su'"
        :topography-url="topographyUrl"
        :topography="topography"
        :disabled="disabled"
        :enlarged="enlarged"
        :selectable="selectable"
        @delete:topography="topographyDeleted"
        v-model:topography="topographyModel"
        v-model:selected="selectedModel">
    </topography-properties-card>
</template>

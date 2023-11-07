<script setup>

import {computed} from "vue";

import {formatExponential} from "topobank/utils/formatting";

const props = defineProps({
    topography: Object
});

const isMetadataIncomplete = computed(() => {
    if (props.topography !== null && props.topography.is_metadata_complete !== undefined) {
        return !props.topography.is_metadata_complete;
    } else {
        return true;
    }
});

const shortReliabilityCutoff = computed(() => {
    return formatExponential(props.topography.short_reliability_cutoff, 2) + ` m`;
});
</script>

<template>
    <div v-if="topography !== null && topography.resolution_y !== null">
        <span class="badge bg-warning ms-1">{{ topography.datafile_format }}</span>
        <span class="badge bg-info ms-2">{{ topography.resolution_x }} &times; {{
                topography.resolution_y
            }} data points</span>
        <span v-if="topography.has_undefined_data" class="badge bg-danger ms-2">undefined data</span>
        <span v-if="isMetadataIncomplete" class="badge bg-danger ms-2">metadata incomplete</span>
        <span v-if="topography.short_reliability_cutoff !== null" class="badge bg-dark ms-2">
                    reliability cutoff {{ shortReliabilityCutoff }}
                </span>
    </div>
    <div v-if="topography !== null && topography.resolution_y === null">
        <div class="badge bg-warning ms-1">{{ topography.datafile_format }}</div>
        <div class="badge bg-info ms-2">{{ topography.resolution_x }} data points</div>
        <span v-if="topography.has_undefined_data" class="badge bg-danger ms-2">undefined data</span>
        <span v-if="isMetadataIncomplete" class="badge bg-danger ms-2">metadata incomplete</span>
        <span v-if="topography.short_reliability_cutoff !== null" class="badge bg-dark ms-2">
                    reliability cutoff {{ shortReliabilityCutoff }}
                </span>
    </div>
</template>

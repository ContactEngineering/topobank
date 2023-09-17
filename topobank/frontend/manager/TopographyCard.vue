<script>

import axios from "axios";

import TopographyErrorCard from "./TopographyErrorCard.vue";
import TopographyPendingCard from "./TopographyPendingCard.vue";
import TopographyPropertiesCard from "./TopographyPropertiesCard.vue";
import TopographyUploadCard from "./TopographyUploadCard.vue";

export default {
    name: 'topography-card',
    components: {
        TopographyErrorCard,
        TopographyPropertiesCard,
        TopographyPendingCard,
        TopographyUploadCard,
    },
    emits: [
        'topography-deleted'
    ],
    props: {
        topography: Object,
        pollingInterval: {
            type: Number,
            default: 1000  // milliseconds
        }
    },
    data() {
        return {
            _topography: this.topography
        }
    },
    mounted() {
        this.scheduleStateCheck();
    },
    methods: {
        scheduleStateCheck() {
            if (this._topography.task_state != 'su' && this._topography.task_state != 'fa') {
                setTimeout(this.checkState, this.pollingInterval);
            }
        },
        checkState() {
            axios.get(this._topography.url).then(response => {
                this._topography = response.data;
                this.scheduleStateCheck();
            });
        },
        topographyDeleted(url) {
            this.$emit('topography-deleted', url);
        }
    }
};
</script>

<template>
    <topography-upload-card v-if="_topography.post_data !== null"
                            :name="_topography.name"
                            :file="_topography.file"
                            :post-data="_topography.post_data"
                            @upload-successful="checkState">
    </topography-upload-card>
    <topography-pending-card v-if="_topography.post_data === null && _topography.task_state != 'su' && _topography.task_state != 'fa'"
                             :url="_topography.url"
                             :name="_topography.name"
                             @topography-deleted="topographyDeleted">
    </topography-pending-card>
    <topography-error-card v-if="_topography.post_data === null && _topography.task_state == 'fa'"
                           :url="_topography.url"
                           :name="_topography.name"
                           :error="_topography.error"
                           @topography-deleted="topographyDeleted">
    </topography-error-card>
    <topography-properties-card v-if="_topography.post_data === null && _topography.task_state == 'su'"
                                :data="_topography"
                                @topography-deleted="topographyDeleted">
    </topography-properties-card>
</template>

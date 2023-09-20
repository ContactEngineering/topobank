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
        'topography-deleted',
        'topography-updated',
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
                this.$emit('topography-updated', this._topography);
                this.scheduleStateCheck();
            });
        },
        topographyDeleted(url) {
            console.log(url);
            this.$emit('topography-deleted', url);
        },
        topographyUpdated(topography) {
            this._topography = topography;
            this.$emit('topography-updated', this._topography);
            this.scheduleStateCheck();
        }
    },
    computed: {
        isUploading() {
            return this._topography.post_data !== undefined && this._topography.post_data !== null
        }
    },
    watch: {
        topography(newValue, oldValue) {
            this._topography = newValue;
            this.scheduleStateCheck();
        }
    }
};
</script>

<template>
    <topography-upload-card
        v-if="isUploading"
        :name="_topography.name"
        :file="_topography.file"
        :post-data="_topography.post_data"
        @upload-successful="checkState">
    </topography-upload-card>
    <topography-pending-card
        v-if="!isUploading && _topography.task_state != 'su' && _topography.task_state != 'fa'"
        :url="_topography.url"
        :name="_topography.name"
        @topography-deleted="topographyDeleted">
    </topography-pending-card>
    <topography-error-card
        v-if="!isUploading && _topography.task_state == 'fa'"
        :url="_topography.url"
        :name="_topography.name"
        :error="_topography.error"
        @topography-deleted="topographyDeleted">
    </topography-error-card>
    <topography-properties-card
        v-if="!isUploading && _topography.task_state == 'su'"
        :data="_topography"
        @topography-deleted="topographyDeleted"
        @topography-updated="topographyUpdated">
    </topography-properties-card>
</template>

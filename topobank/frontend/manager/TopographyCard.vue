<script>

import axios from "axios";

import {BSpinner} from "bootstrap-vue-next";

import TopographyErrorCard from "./TopographyErrorCard.vue";
import TopographyPendingCard from "./TopographyPendingCard.vue";
import TopographyPropertiesCard from "./TopographyPropertiesCard.vue";
import TopographyUploadCard from "./TopographyUploadCard.vue";

export default {
    name: 'topography-card',
    components: {
        BSpinner,
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
            if (this._topography === null) {
                this.checkState();
            } else if (this._topography.task_state !== 'su' && this._topography.task_state !== 'fa') {
                setTimeout(this.checkState, this.pollingInterval);
            }
        },
        checkState() {
            const topographyUrl = this._topography === null ? this.topographyUrl : this._topography.url;
            axios.get(topographyUrl).then(response => {
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
            return this._topography !== null &&
                this._topography.post_data !== undefined &&
                this._topography.post_data !== null;
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
    <div v-if="_topography === null"
         class="card mb-1">
        <div class="card-body">
            <b-spinner small></b-spinner>
            Querying topography data, please wait...
        </div>
    </div>
    <topography-upload-card
        v-if="_topography !== null && isUploading"
        :name="_topography.name"
        :file="_topography.file"
        :post-data="_topography.post_data"
        @upload-successful="checkState">
    </topography-upload-card>
    <topography-pending-card
        v-if="_topography !== null && !isUploading && _topography.task_state != 'su' && _topography.task_state != 'fa'"
        :url="_topography.url"
        :name="_topography.name"
        @topography-deleted="topographyDeleted">
    </topography-pending-card>
    <topography-error-card
        v-if="_topography !== null && !isUploading && _topography.task_state == 'fa'"
        :url="_topography.url"
        :name="_topography.name"
        :error="_topography.error"
        @topography-deleted="topographyDeleted">
    </topography-error-card>
    <topography-properties-card
        v-if="_topography !== null && !isUploading && _topography.task_state == 'su'"
        :data="_topography"
        :enlarged="enlarged"
        @topography-deleted="topographyDeleted"
        @topography-updated="topographyUpdated">
    </topography-properties-card>
</template>

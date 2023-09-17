<script>

import axios from "axios";
import TopographyErrorCard from "./TopographyErrorCard.vue";
import TopographyPendingCard from "./TopographyPendingCard.vue";
import TopographyPropertiesCard from "./TopographyPropertiesCard.vue";

export default {
    name: 'topography-card',
    components: {
        TopographyPropertiesCard,
        TopographyPendingCard,
        TopographyErrorCard
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
    <topography-pending-card v-if="_topography.task_state != 'su' && _topography.task_state != 'fa'"
                             :url="_topography.url"
                             :name="_topography.name"
                             @topography-deleted="topographyDeleted">
    </topography-pending-card>
    <topography-error-card v-if="_topography.task_state == 'fa'"
                           :url="_topography.url"
                           :name="_topography.name"
                           :error="_topography.error"
                           @topography-deleted="topographyDeleted">
    </topography-error-card>
    <topography-properties-card v-if="_topography.task_state == 'su'"
                                :data="_topography"
                                @topography-deleted="topographyDeleted">
    </topography-properties-card>
</template>

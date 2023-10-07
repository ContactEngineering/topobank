<script>

import axios from "axios";

import TopographyPropertiesCard from "./TopographyPropertiesCard.vue";

export default {
    name: 'topography-detail',
    components: {
        TopographyPropertiesCard
    },
    props: {
        topographyUrl: String
    }
};
</script>

<template>
    <div class="container">
        <topography-properties-card :topography-url="topographyUrl"
                                    :enlarged="true">
        </topography-properties-card>
    </div>
</template>

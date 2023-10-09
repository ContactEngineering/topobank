<script>

import axios from "axios";

import {BSpinner, BTab, BTabs} from "bootstrap-vue-next";

import DeepZoomImage from "../components/DeepZoomImage.vue";
import DropZone from "../components/DropZone.vue";
import LineScanPlot from "../components/LineScanPlot.vue";

import BandwidthPlot from "./BandwidthPlot.vue";
import SurfaceDescription from "./SurfaceProperties.vue";
import SurfacePermissions from "./SurfacePermissions.vue";
import TopographyBadges from "./TopographyBadges.vue";
import TopographyCard from "./TopographyCard.vue";
import {subjectsToBase64} from "topobank/utils/api";

export default {
    name: 'topography-detail',
    components: {
        BandwidthPlot,
        BSpinner,
        BTab,
        BTabs,
        DeepZoomImage,
        DropZone,
        LineScanPlot,
        SurfaceDescription,
        SurfacePermissions,
        TopographyBadges,
        TopographyCard
    },
    props: {
        topographyUrl: String
    },
    data() {
        return {
            _topography: null
        }
    },
    mounted() {
        this.updateCard();
    },
    methods: {
        updateCard() {
            /* Fetch JSON describing the card */
            axios.get(this.topographyUrl).then(response => {
                this._topography = response.data;
            });
        },
    },
    computed: {
        base64Subjects() {
            return subjectsToBase64({topography: [this._topography.id]});
        }
    }
};
</script>

<template>
    <div class="container">
        <div class="row">
            <div class="col-12">
                <div v-if="_topography === null"
                     class="card mb-1">
                    <div class="card-body">
                        <b-spinner small></b-spinner>
                        Querying topography data, please wait...
                    </div>
                </div>
                <b-tabs v-if="_topography !== null"
                        class="nav-pills-custom"
                        content-class="w-100"
                        fill
                        pills
                        vertical>
                    <b-tab title="Visualization">
                        <line-scan-plot v-if="_topography.size_y === null"
                                        :topography="_topography">
                        </line-scan-plot>
                        <deep-zoom-image v-if="_topography.size_y !== null"
                                         :colorbar="true"
                                         :prefix-url="`${_topography.url}dzi/`">
                        </deep-zoom-image>
                    </b-tab>
                    <b-tab title="Properties">
                        <topography-card :topography="_topography"
                                         :enlarged="true">
                        </topography-card>
                    </b-tab>
                    <template #tabs-end>
                        <hr/>
                        <div class="card mt-2">
                            <div class="card-body">
                                <topography-badges :topography="_topography"></topography-badges>
                                <div class="btn-group-vertical mt-2 w-100" role="group">
                                    <a :href="`/analysis/html/list/?subjects=${base64Subjects}`"
                                       class="btn btn-outline-secondary btn-block">
                                        Analyze this measurement
                                    </a>

                                    <a :href="_topography.datafile"
                                       class="btn btn-outline-secondary btn-block">
                                        <i class="fa fa-download"></i> Download
                                    </a>

                                    <a href="#"
                                       class="btn btn-outline-danger btn-block">
                                        <i class="fa fa-trash"></i> Delete
                                    </a>
                                </div>
                            </div>
                        </div>
                    </template>
                </b-tabs>
            </div>
        </div>
    </div>
</template>

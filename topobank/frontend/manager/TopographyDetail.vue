<script>

import axios from "axios";

import {BTab, BTabs} from "bootstrap-vue-next";

import BandwidthPlot from "topobank/manager/BandwidthPlot.vue";
import DropZone from "topobank/components/DropZone.vue";
import SurfaceDescription from "topobank/manager/SurfaceProperties.vue";
import SurfacePermissions from "topobank/manager/SurfacePermissions.vue";
import TopographyCard from "topobank/manager/TopographyCard.vue";

export default {
    name: 'topography-detail',
    components: {
        BandwidthPlot,
        BTab,
        BTabs,
        DropZone,
        SurfaceDescription,
        SurfacePermissions,
        TopographyCard,
    },
    props: {
        topographyUrl: String
    }
};
</script>

<template>
    <div class="container">
        <div class="row">
            <div class="col-12">
                <b-tabs class="nav-pills-custom"
                        content-class="w-100"
                        fill
                        pills
                        vertical>
                    <b-tab title="Visualization">
                    </b-tab>
                    <b-tab title="Properties">
                        <topography-card :topography-url="topographyUrl"
                                                    :enlarged="true">
                        </topography-card>
                    </b-tab>
                    <template #tabs-end>
                        <hr/>
                        <div class="card mt-2">
                            <div class="card-body">
                                <div class="btn-group-vertical mt-2 w-100" role="group">
                                    <a :href="`/analysis/html/list/?subjects=`"
                                       class="btn btn-outline-secondary btn-block">
                                        Analyze this measurement
                                    </a>

                                    <a href="`/manager/${surfaceId}/download`"
                                       class="btn btn-outline-secondary btn-block">
                                        Download
                                    </a>

                                    <a href="#"
                                       class="btn btn-outline-danger btn-block">
                                        Delete
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

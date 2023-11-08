<script setup>

import {v4 as uuid4} from 'uuid';

import axios from "axios";
import {onMounted, ref} from "vue";
import {ColumnDataSource, Plotting} from "@bokeh/bokehjs";
import {NetCDFReader} from 'netcdfjs';

import {applyDefaultBokehStyle} from "../utils/bokeh";

const props = defineProps({
    topography: Object
});

const uid = ref(uuid4());

onMounted(() => {
    axios.get(props.topography.squeezed_datafile, {responseType: 'arraybuffer'})
        .then(response => {
            const netcdfReader = new NetCDFReader(response.data);
            const x = netcdfReader.getDataVariable('x');
            const heights = netcdfReader.getDataVariable('heights');

            const figure = new Plotting.Figure({
                x_axis_label: `Position (${props.topography.unit})`,
                y_axis_label: `Height (${props.topography.unit})`,
                output_backend: 'svg',
                sizing_mode: 'stretch_width'
            });

            // Apply default settings
            applyDefaultBokehStyle(figure);

            // Construct data source
            const plot_source = new ColumnDataSource({
                data: {
                    x: x,
                    heights: heights
                }
            });

            // Construct glyphs
            figure.line({
                x: {field: 'x'},
                y: {field: 'heights'},
                source: plot_source
            });

            // Render to component
            Plotting.show(figure, `#plot-${uid.value}`);
        });
});

</script>

<template>
    <div :id="`plot-${uid}`"></div>
</template>

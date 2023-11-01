<script setup>

import {v4 as uuid4} from 'uuid';

import {onMounted, ref, watch} from "vue";

import {ColumnDataSource, HoverTool, Plotting} from "@bokeh/bokehjs";

import {applyDefaultBokehStyle} from "../utils/bokeh";

const uid = ref(uuid4());

const props = defineProps({
    topographies: {
        type: Object,
        default: []
    }
});

// Hover tool
const hover_tool = new HoverTool({
    'tooltips': '<div class="bandwidth-hover-box">' +
        '<img src="@thumbnail" height="80" width="80" alt="Thumbnail is missing">' +
        '<span>@name</span>' +
        '</div>'
});

// Bokeh figure
const figure = new Plotting.Figure({
    x_axis_label: 'Bandwidth (m)',
    x_axis_type: 'log',
    output_backend: 'svg',
    sizing_mode: 'stretch_width',
    tools: [hover_tool],
    toolbar_location: null,
});

// Construct data source
const bw_source = new ColumnDataSource({
    data: {
        y: [],
        left: [],
        cutoff: [],
        right: [],
        name: [],
        thumbnail: [],
        link: []
    }
});

// Apply default settings
applyDefaultBokehStyle(figure);

// Adjust properties not accessible in the constructor
figure.yaxis.visible = false;
figure.grid.visible = false;
figure.outline_line_color = null;
figure.legend.location = "top_left";
figure.legend.title = "Measurement artifacts";
figure.legend.title_text_font_style = "bold";
figure.legend.background_fill_color = "#f0f0f0";
figure.legend.border_line_width = 3;
figure.legend.border_line_cap = "round";

// Construct glyphs
figure.hbar({
    y: {field: 'y'},
    left: {field: 'left'},
    right: {field: 'right'},
    height: 1.0,
    color: '#2c90d9',
    name: 'bandwidths',
    legend_label: "Reliable",
    level: "underlay",
    source: bw_source
});

figure.hbar({
    y: {field: 'y'},
    left: {field: 'left'},
    right: {field: 'cutoff'},
    height: 1.0,
    color: '#dc3545',
    name: 'bandwidths',
    legend_label: "Unreliable",
    level: "underlay",
    source: bw_source
});

function setPlotData(topographies) {
    // Sort topographies
    const left = topographies.map(t => t.bandwidth_lower);
    const argsort = left.map((v, i) => [v, i]).sort((a, b) => a[0] - b[0]).map(a => a[1]);
    let y = Array(argsort.length);
    for (const i of argsort.keys()) {
        y[argsort[i]] = i;
    }

    // Construct data source
    bw_source.data = {
        y: y,
        left: left,
        cutoff: topographies.map(t => t.short_reliability_cutoff),
        right: topographies.map(t => t.bandwidth_upper),
        name: topographies.map(t => t.name),
        thumbnail: topographies.map(t => t.thumbnail),
        link: topographies.map(t => `/manager/html/topography/?topography=${t.id}`),
    };
}

onMounted(() => {
    // Render to component
    Plotting.show(figure, `#plot-${uid.value}`);

    // Set data
    setPlotData(props.topographies);
});

watch(props.topographies, (newValue, oldValue) => {
    console.log('topographies changed');
    setPlotData(newValue);
});

</script>

<template>
    <div :id="`plot-${uid}`"></div>
</template>

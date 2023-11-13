<script setup>

import {v4 as uuid4} from 'uuid';
import {onMounted, ref, watch} from "vue";
import {ColumnDataSource, HoverTool, OpenURL, Plotting, TapTool} from "@bokeh/bokehjs";
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
    'tooltips': '<div style="width: 7rem;">' +
        '<img src="@thumbnail" width="100%" alt="Thumbnail is missing">' +
        '<span>@name</span>' +
        '</div>'
});

// Tap tool
const tap_tool = new TapTool({
    callback: new OpenURL({
        url: "@link",
        same_tab: true
    })
});

// Bokeh figure
const figure = new Plotting.Figure({
    x_axis_label: 'Bandwidth (m)',
    x_axis_type: 'log',
    output_backend: 'svg',
    sizing_mode: 'stretch_width',
    tools: [hover_tool, tap_tool],
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
    // Filter nulls
    const filtered_topographies = topographies.filter(t => t !== null);

    // Sort topographies
    const left = filtered_topographies.map(t => t.bandwidth_lower);
    const argsort = left.map((v, i) => [v, i]).sort((a, b) => a[0] - b[0]).map(a => a[1]);
    let y = Array(argsort.length);
    for (const i of argsort.keys()) {
        y[argsort[i]] = i;
    }

    // Construct data source
    bw_source.data = {
        y: y,
        left: left,
        cutoff: filtered_topographies.map(t => t.short_reliability_cutoff),
        right: filtered_topographies.map(t => t.bandwidth_upper),
        name: filtered_topographies.map(t => t.name),
        thumbnail: filtered_topographies.map(t => t.thumbnail),
        link: filtered_topographies.map(t => `/manager/html/topography/?topography=${t.id}`),
    };
}

onMounted(() => {
    // Render to component
    Plotting.show(figure, `#plot-${uid.value}`);

    // Set data
    setPlotData(props.topographies);
});

watch(props.topographies, (newValue, oldValue) => {
    setPlotData(newValue);
});

</script>

<template>
    <div :id="`plot-${uid}`"></div>
</template>

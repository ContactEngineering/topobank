<script>

import {v4 as uuid4} from 'uuid';

import {ColumnDataSource, HoverTool, Plotting} from "@bokeh/bokehjs";

export default {
    name: 'bandwidth-plot',
    props: {
        topographies: {
            type: Object,
            default: []
        },
        uid: {
            type: String,
            default() {
                return uuid4();
            }
        }
    },
    mounted() {
        this.buildPlot();
    },
    methods: {
        buildPlot() {
            // Hover tool
            const hover_tool = new HoverTool({
                'tooltips': '<div class="bandwidth-hover-box">' +
                    '<img src="@thumbnail" height="80" width="80" alt="Thumbnail is missing">' +
                    '<span>@name</span>' +
                    '</div>'
            });

            // Create Bokeh figure
            const figure = new Plotting.Figure({
                x_axis_label: 'Bandwidth (m)',
                x_axis_type: 'log',
                output_backend: 'svg',
                //sizing_mode: 'stretch_width',
                tools: [hover_tool],
                toolbar_location: null,
            });

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

            console.log(this.topographies);

            // Sort topographies
            const left = this.topographies.map(t => t.bandwidth_lower);
            const argsort = left.map((v, i) => [v, i]).sort((a, b) => a[0] - b[0]).map(a => a[1]);
            let y = Array(argsort.length);
            for (const i of argsort.keys()) {
                console.log(i);
                y[argsort[i]] = i;
            }

            // Construct data source
            const bw_source = new ColumnDataSource({
                data: {
                    y: y,
                    left: left,
                    right: this.topographies.map(t => t.bandwidth_upper),
                    name: this.topographies.map(t => t.name),
                    thumbnail: this.topographies.map(t => t.thumbnail)
                    //topography_link: bw_topography_links,
                }
            });

            // Construct glyphs
            figure.hbar({
                y: {field: 'y'},
                left: {field: 'left'},
                right: {field: 'right'},
                height: 1.0,
                color: '#2c90d9',
                name: 'bandwidths',
                legend_label: "Reliable bandwidth",
                level: "underlay",
                source: bw_source
            });

            // Render to component
            Plotting.show(figure, `#plot-${this.uid}`);
        }
    }
};
</script>

<template>
    <div :id="`plot-${uid}`"></div>
</template>

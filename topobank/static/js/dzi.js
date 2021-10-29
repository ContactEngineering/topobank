/**
 * Helper function for visualizing 2D maps (topography, pressure, etc.) using
 * Deep Zoom Image files and OpenSeadragon.
 */

function visualizeMap(id, prefixUrl, scaleBar = null, colorBar = null) {
    viewer = new OpenSeadragon.Viewer({
        id: id,
        prefixUrl: prefixUrl,
        tileSources: [prefixUrl + 'dzi.xml'],
        showNavigator: true,
        navigatorPosition: 'TOP_LEFT',
        navigatorSizeRatio: 0.1,
        showNavigationControl: false,
        wrapHorizontal: false,
        wrapVertical: false,
        minZoomImageRatio: 0.5,
        maxZoomPixelRatio: 5.0,
    });

    // Add a scale bar
    if (scaleBar) {
        viewer.scalebar({
            type: OpenSeadragon.ScalebarType.MICROSCOPY,
            pixelsPerMeter: scaleBar.pixelsPerMeter,
            minWidth: "75px",
            location: OpenSeadragon.ScalebarLocation.BOTTOM_LEFT,
            xOffset: 10,
            yOffset: 10,
            stayInsideImage: true,
            color: "black",
            fontColor: "black",
            backgroundColor: "rgba(255, 255, 255, 0.5)",
            fontSize: "medium",
            barThickness: 2
        });
    }

    // Add a color bar
    if (colorBar) {
        var div = $('#' + colorBar.id);
        div.empty();
        div.append($('<div/>', {
            class: 'zoom-colorbar-title',
            html: colorBar.title
        }));
        var tickDiv = $('<div/>', {
            class: 'zoom-colorbar background-viridis'
        });
        var tickLabelDiv = $('<div/>', {
            class: 'zoom-colorbar'
        });
        for (const tick of colorBar.ticks) {
            console.log(tick);
            tickDiv.append($('<div/>', {
                class: 'zoom-colorbar-tick',
                style: 'top: ' + tick.position + ';'
            }));
            tickLabelDiv.append($('<div/>', {
                class: 'zoom-colorbar-text',
                style: 'top: ' + tick.position + ';',
                html: tick.label
            }));
        }
        div.append(tickDiv);
        div.append(tickLabelDiv);
    }
}

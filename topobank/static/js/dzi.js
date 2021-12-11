/**
 * Helper function for visualizing 2D maps (topography, pressure, etc.) using
 * Deep Zoom Image files and OpenSeadragon.
 */

function visualizeMap(id, prefixUrl, colorBar = null, downloadButton = null, retryDelay = 5000) {
    $('#' + id).empty();
    $('#' + id).html('<span class="spinner"></span>Creating and loading zoomable image, please wait...')
    var requestDzi = function() {
        $.ajax({
            url: prefixUrl + 'dzi.json',
            type: 'get',
            success: function (meta) {
                $('#' + id).empty();

                meta.Image.Url = prefixUrl + 'dzi_files/';

                viewer = new OpenSeadragon.Viewer({
                    id: id,
                    tileSources: meta,
                    showNavigator: true,
                    navigatorPosition: 'TOP_LEFT',
                    navigatorSizeRatio: 0.1,
                    wrapHorizontal: false,
                    wrapVertical: false,
                    minZoomImageRatio: 0.5,
                    maxZoomPixelRatio: 5.0,
                    crossOriginPolicy: "Anonymous",
                    showNavigationControl: false
                });

                // Add a scale bar
                if (meta.Image.PixelsPerMeter) {
                    viewer.scalebar({
                        type: OpenSeadragon.ScalebarType.MICROSCOPY,
                        pixelsPerMeter: (meta.Image.PixelsPerMeter.Width + meta.Image.PixelsPerMeter.Height) / 2,
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
                if (colorBar && meta.Image.ColorbarRange && meta.Image.ColorbarTitle && meta.Image.Colormap) {
                    var colorBarDiv = $('#' + colorBar);
                    colorBarDiv.empty();
                    colorBarDiv.append($('<div/>', {
                        class: 'dzi-colorbar-title',
                        html: meta.Image.ColorbarTitle
                    }));
                    var tickDiv = $('<div/>', {
                        class: 'dzi-colorbar-column background-' + meta.Image.Colormap
                    });
                    var tickLabelDiv = $('<div/>', {
                        class: 'dzi-colorbar-column'
                    });

                    mn = meta.Image.ColorbarRange.Minimum;
                    mx = meta.Image.ColorbarRange.Maximum;

                    log10_tick_dist = (Math.round(Math.log10(mx - mn)) - 1);
                    fraction_digits = log10_tick_dist > 0 ? 0 : -log10_tick_dist;
                    tick_dist = 10 ** log10_tick_dist;
                    nb_ticks = Math.trunc((mx - mn) / tick_dist) + 1;

                    while (nb_ticks > 15) {
                        tick_dist *= 2;
                        nb_ticks = Math.trunc((mx - mn) / tick_dist) + 1;
                    }

                    for (let i = 0; i < nb_ticks; i++) {
                        v = Math.trunc(mn / tick_dist) * tick_dist + tick_dist * i;
                        relpos = (mx - v) * 100 / (mx - mn);
                        if (relpos > 0 && relpos < 100) {
                            tickDiv.append($('<div/>', {
                                class: 'dzi-colorbar-tick',
                                style: 'top: ' + relpos + '%;'
                            }));
                            tickLabelDiv.append($('<div/>', {
                                class: 'dzi-colorbar-text',
                                style: 'top: ' + relpos + '%;',
                                html: v.toFixed(fraction_digits)
                            }));
                        }
                    }
                    colorBarDiv.append(tickDiv);
                    colorBarDiv.append(tickLabelDiv);
                }

                // Image download
                if (downloadButton) {
                    $('#' + downloadButton).on('click', function () {
                        var imgCanvas = viewer.drawer.canvas;
                        var canvas = document.createElement("canvas");
                        canvas.width = imgCanvas.width;
                        canvas.height = imgCanvas.height;
                        var ctx = canvas.getContext('2d');
                        ctx.drawImage(imgCanvas, 0, 0);
                        var scalebarCanvas = viewer.scalebarInstance.getAsCanvas();
                        var location = viewer.scalebarInstance.getScalebarLocation();

                        ctx.drawImage(scalebarCanvas, location.x, location.y);

                        imgCanvas.toBlob(function (blob) {
                            saveAs(blob, "screenshot.png");
                        });
                    });
                }
            },
            error: function (xhr, textStatus, errorThrown) {
                /**
                 * If an error occurs *not* because of XMLHttpRequest.abort(), show an
                 * error message. Do not show error on .abort(). See also
                 * https://developer.mozilla.org/en-US/docs/Web/API/XMLHttpRequest/abort
                 * */
                if (xhr.status == 0) {
                    console.log("Canceled plot generation.");
                    $('#' + id).html(`
                        Canceled loading of plot.
                      `)
                } else if (xhr.status == 404) {
                    /* 404 indicates the resource is not yet available, retryYou */
                    setTimeout(requestDzi, retryDelay);
                } else {
                    /* Treat any other code as an actual error */
                    console.error("Could not create plot: " + errorThrown + " " + xhr.status + " " + xhr.responseText);
                    $('#' + id).html(`
                        <div class='alert alert-danger'>
                            Could not load plot data. Error: ${errorThrown}
                        </div>
                      `);
                }
            }
        });
    };

    requestDzi();
}

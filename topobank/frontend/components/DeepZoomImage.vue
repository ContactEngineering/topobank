<script>
/**
* Vue component for visualizing 2D maps (topography, pressure, etc.) using
* Deep Zoom Image files and OpenSeadragon.
*/

export default {
  name: 'deep-zoom-image',
  inject: ['eventHub'],
  props: {
    prefixUrl: String,
    colorbar: {
      type: Boolean,
      default: false
    },
    downloadButton: {
      type: Boolean,
      default:
          false
    },
    retryDelay: {
      type: Number,
      default:
          5000
    }
  },
  data: function () {
    return {
      uuid: null,
      viewer: null,
      isLoaded: false,
      colorbarTitle: null,
      colormap: null,
      colorbarTicks: [],
      errorMessage: null
    };
  },
  created: function () {
    this.uuid = crypto.randomUUID();
  },
  mounted: function () {
    this.eventHub.on('download-dzi', this.download);
    this.requestDzi();
  },
  watch: {
    prefixUrl: function () {
      // We are loading a new image
      this.isLoaded = false;

      // Prefix URL changed - request new image and replace current one
      fetch(this.prefixUrl + 'dzi.json').then(response => {
        return response.json();  // Image metadata
      }).then(meta => {
        meta.Image.Url = this.prefixUrl + 'dzi_files/';  // Set URL for DZI files

        this.viewer.addTiledImage({
          tileSource: meta,
          success: () => {
            this.isLoaded = true;
          }
        });
      });
    }
  },
  methods: {
    requestDzi: function () {
      fetch(this.prefixUrl + 'dzi.json').then(response => {
        if (response.ok) {
          return response.json();
        }
        let err = Error("DZI images not ready yet.");
        err.response = response;
        throw err;
      }).then(meta => {
        meta.Image.Url = this.prefixUrl + 'dzi_files/';  // Set URL for DZI files

        // Create OpenSeadragon viewer
        this.viewer = new OpenSeadragon.Viewer({
          id: "dzi-view-" + this.uuid,
          tileSources: meta,
          showNavigator: true,
          navigatorPosition: 'TOP_LEFT',
          navigatorSizeRatio: 0.1,
          wrapHorizontal: false,
          wrapVertical: false,
          minZoomImageRatio: 0.5,
          maxZoomPixelRatio: 5.0,
          crossOriginPolicy: "Anonymous",
          showNavigationControl: false,
        });

        // Add a scale bar
        if (meta.Image.PixelsPerMeter) {
          this.viewer.scalebar({
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

        // Configure color bar
        if (this.colorbar && meta.Image.ColorbarRange && meta.Image.ColorbarTitle && meta.Image.Colormap) {
          // Set title and colormap
          this.colorbarTitle = meta.Image.ColorbarTitle;
          this.colormap = meta.Image.Colormap;

          // Generate tick positions and labels
          let mn = meta.Image.ColorbarRange.Minimum;
          let mx = meta.Image.ColorbarRange.Maximum;

          let log10_tick_dist = (Math.round(Math.log10(mx - mn)) - 1);
          let fraction_digits = log10_tick_dist > 0 ? 0 : -log10_tick_dist;
          let tick_dist = 10 ** log10_tick_dist;
          let nb_ticks = Math.trunc((mx - mn) / tick_dist) + 1;

          while (nb_ticks > 15) {
            tick_dist *= 2;
            nb_ticks = Math.trunc((mx - mn) / tick_dist) + 1;
          }

          for (let i = 0; i < nb_ticks; i++) {
            let v = Math.trunc(mn / tick_dist) * tick_dist + tick_dist * i;
            let relpos = (mx - v) * 100 / (mx - mn);
            if (relpos > 0 && relpos < 100) {
              this.colorbarTicks.push({relpos: relpos, label: v.toFixed(fraction_digits)});
            }
          }
        }

        this.isLoaded = true;
      }).catch(error => {
        let error_has_response = "response" in error;
        /**
         * If an error occurs *not* because of XMLHttpRequest.abort(), show an
         * error message. Do not show error on .abort(). See also
         * https://developer.mozilla.org/en-US/docs/Web/API/XMLHttpRequest/abort
         * */
        console.log(error);

        if (error_has_response && (error.response.status == 0)) {
          this.errorMessage = "Canceled loading of plot.";
        } else if (error_has_response && (error.response.status == 404)) {
          /* 404 indicates the resource is not yet available, retry */
          console.log("Resource not yet available, retrying..")
          setTimeout(this.requestDzi, this.retryDelay);
        } else {
          /* Treat any other code as an actual error */
          this.errorMessage = error.message;
        }
      });
    },
    download: function () {
      // Image download. Code has been adapted from:
      // https://github.com/KTGLeiden/Openseadragon-screenshot/blob/master/openseadragonScreenshot.js
      var downloadImage = () => {
        this.viewer.world.getItemAt(0).removeAllHandlers('fully-loaded-change');

        var imgCanvas = this.viewer.drawer.canvas;
        var downloadCanvas = document.createElement("canvas");
        downloadCanvas.width = imgCanvas.width;
        downloadCanvas.height = imgCanvas.height;

        var context = downloadCanvas.getContext('2d');
        context.drawImage(imgCanvas, 0, 0);

        var scalebarCanvas = this.viewer.scalebarInstance.getAsCanvas();
        var location = this.viewer.scalebarInstance.getScalebarLocation();
        context.drawImage(scalebarCanvas, location.x, location.y);

        downloadCanvas.toBlob(function (blob) {
          saveAs(blob, "screenshot.png");
        });
      }

      if (this.viewer.world.getItemAt(0).getFullyLoaded()) {
        downloadImage();
      } else {
        this.viewer.world.getItemAt(0).addHandler('fully-loaded-change', downloadImage);
      }
    }
  }
}
</script>

<template>
  <div class="dzi-container">
    <div :id='"dzi-view-" + uuid' class="dzi-view">
      <div v-if="!isLoaded && errorMessage === null">
        <span class="spinner"></span>Creating and loading zoomable image, please wait...
      </div>
      <div v-if="errorMessage !== null" class='alert alert-danger'>
        Could not load plot data. Error: {{ errorMessage }}
      </div>
    </div>
    <div v-if="colorbar && isLoaded" class="dzi-colorbar">
      <div class="dzi-colorbar-title">
        {{ colorbarTitle }}
      </div>
      <div :class='"dzi-colorbar-column background-" + colormap'>
        <div v-for="tick in colorbarTicks" class="dzi-colorbar-tick" :style='"top: " + tick.relpos + "%;"'></div>
      </div>
      <div class="dzi-colorbar-column">
        <div v-for="tick in colorbarTicks" class="dzi-colorbar-text" :style='"top: " + tick.relpos + "%;"'>
          {{ tick.label }}
        </div>
      </div>
    </div>
  </div>
</template>

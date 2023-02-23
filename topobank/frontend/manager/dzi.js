import {createApp} from 'vue';
import DeepZoomImage from '../components/DeepZoomImage.vue';

/**
 * Wrapper for an OpenSeadragon instance (with a scale bar)
 */
export function createDeepZoomImage(el, props) {
    let app = createApp(DeepZoomImage, props);
    app.mount(el);
    return app;
}

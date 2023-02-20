import {createApp} from 'vue';
import DeepZoomImage from './DeepZoomImage.vue';

export function createDeepZoomImage(el, props) {
    let app = createApp(DeepZoomImage, props);
    app.mount(el);
    return app;
}

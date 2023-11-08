import axios from "axios";
import {createApp} from 'vue';

import SurfaceDetail from './SurfaceDetail.vue';

export function createSurfaceDetailApp(el, csrfToken, props) {
    let app = createApp(SurfaceDetail, props);
    axios.defaults.headers.common['X-CSRFToken'] = csrfToken;
    app.provide('csrfToken', csrfToken);
    app.mount(el);
    return app;
}

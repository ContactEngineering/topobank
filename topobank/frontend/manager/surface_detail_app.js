import {createApp} from 'vue';

import SurfaceDetail from './SurfaceDetail.vue';

export function createSurfaceDetailApp(el, csrfToken, props) {
    let app = createApp(SurfaceDetail, props);
    app.provide('csrfToken', csrfToken);
    app.mount(el);
    return app;
}

import axios from "axios";
import {createApp} from 'vue';

import TopographyDetail from './TopographyDetail.vue';

export function createTopographyDetailApp(el, csrfToken, props) {
    let app = createApp(TopographyDetail, props);
    axios.defaults.headers.common['X-CSRFToken'] = csrfToken;
    app.provide('csrfToken', csrfToken);
    app.mount(el);
    return app;
}

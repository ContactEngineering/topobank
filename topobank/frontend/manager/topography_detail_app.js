import axios from "axios";
import {createApp} from 'vue';

import mitt from "mitt";

import TopographyDetail from './TopographyDetail.vue';

const eventHub = mitt();


export function createTopographyDetailApp(el, csrfToken, props) {
    let app = createApp(TopographyDetail, props);
    axios.defaults.headers.common['X-CSRFToken'] = csrfToken;
    app.provide('csrfToken', csrfToken);
    app.provide('eventHub', eventHub);
    app.mount(el);
    return app;
}

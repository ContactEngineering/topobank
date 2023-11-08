import {createApp} from 'vue';
import VueCookies from 'vue-cookies';

import AnalysisResultsList from './AnalysisResultsList.vue';
import AnalysisResultsDetail from './AnalysisResultsDetail.vue';

import axios from "axios";
import mitt from 'mitt';

const eventHub = mitt();

export function createAnalysisResultsListApp(el, csrfToken, props) {
    let app = createApp(AnalysisResultsList, props);
    app.use(VueCookies);
    axios.defaults.headers.common['X-CSRFToken'] = csrfToken;
    app.provide('csrfToken', csrfToken);
    app.provide('eventHub', eventHub);
    app.mount(el);
    return app;
}

export function createAnalysisResultsDetailApp(el, csrfToken, props) {
    let app = createApp(AnalysisResultsDetail, props);
    app.use(VueCookies);
    axios.defaults.headers.common['X-CSRFToken'] = csrfToken;
    app.provide('csrfToken', csrfToken);
    app.provide('eventHub', eventHub);
    app.mount(el);
    return app;
}

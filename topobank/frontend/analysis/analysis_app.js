import {createApp} from 'vue';
import AnalysisResultsList from './AnalysisResultsList.vue';
import AnalysisResultsDetail from './AnalysisResultsDetail.vue';

export function createAnalysisResultsListApp(el, props) {
    let app = createApp(AnalysisResultsList, props);
    app.mount(el);
    return app;
}

export function createAnalysisResultsDetailApp(el, props) {
    let app = createApp(AnalysisResultsDetail, props);
    app.mount(el);
    return app;
}

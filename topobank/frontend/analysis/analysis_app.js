import {createApp} from 'vue';
import AnalysisApp from './AnalysisApp.vue';

export function createAnalysisApp(el, props) {
    let app = createApp(AnalysisApp, props);
    app.mount(el);
    return app;
}

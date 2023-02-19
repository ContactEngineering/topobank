import {createApp} from 'vue';
import SearchResults from './SearchResults.vue';

export function create_search_results_app(el, event_hub, props) {
    let app = createApp(SearchResults, props);
    app.provide('event_hub', event_hub);
    app.mount(el);
    return app;
}

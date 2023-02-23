import {createApp} from 'vue';
import SearchResults from './SearchResults.vue';

/**
 * Used to display search results/list of digital surface twins
 */
export function createSearchResultsApp(el, event_hub, props) {
    let app = createApp(SearchResults, props);
    app.provide('event_hub', event_hub);
    app.mount(el);
    return app;
}

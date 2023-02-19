import {createApp} from 'vue';
import SearchResults from './SearchResults.vue';

export function create_search_results_app(el, props) {
    createApp(SearchResults, props).mount(el);
}

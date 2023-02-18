import {createApp} from 'vue';
import SearchResults from './SearchResults.vue';

export function create_search_results_app(el, props) {
    createApp(SearchResults, {
        base_urls: props.base_urls,
        current_page: props.current_page,
        search_term: props.search_term,
        category_filter_choices: props.category_filter_choices,
        sharing_status_filter_choices: props.sharing_status_filter_choices,
        is_loading: props.is_loading,
        initial_page_size: props.page_size,
        initial_category: props.category_filter_choices,
        initial_sharing_status: props.sharing_status,
        initial_tree_mode: props.tree_mode
    }).mount(el);
}

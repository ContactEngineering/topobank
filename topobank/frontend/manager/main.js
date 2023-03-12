import {createApp} from 'vue';

import Basket from './Basket.vue'
import DeepZoomImage from '../components/DeepZoomImage.vue';
import SearchResults from './SearchResults.vue';

/**
 * Used to display "basket" on top if screen for all selected items in session
 */
export function createBasketApp(el, event_hub, props) {
    let app = createApp(Basket, props);
    app.provide('event_hub', event_hub);
    app.mount(el);
    return app;
}

/**
 * Wrapper for an OpenSeadragon instance (with a scale bar)
 */
export function createDeepZoomImage(el, props) {
    let app = createApp(DeepZoomImage, props);
    app.mount(el);
    return app;
}

/**
 * Used to display search results/list of digital surface twins
 */
export function createSearchResultsApp(el, event_hub, props) {
    let app = createApp(SearchResults, props);
    app.provide('event_hub', event_hub);
    app.mount(el);
    return app;
}

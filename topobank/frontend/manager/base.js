import jQuery from 'jquery';

import {createApp} from 'vue';

// TODO: Bootstrap can be imported here but does not register event handlers globally
//import * as bootstrap from 'bootstrap';
import * as Bokeh from '@bokeh/bokehjs';

import DeepZoomImage from '../components/DeepZoomImage.vue';

import Basket from './Basket.vue'
import SearchResults from './SearchResults.vue';

import 'topobank/scss/custom.scss';

/**
 * Make jQuery and Bokeh available globally
 */

window.$ = window.jQuery = jQuery;
window.Bokeh = Bokeh;
//window.bootstrap = bootstrap;

/**
 * Enable Bootstrap data API
 */

//jQuery(document).on('.data-api');

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

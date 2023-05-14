import jQuery from 'jquery';
window.$ = window.jQuery = jQuery;

// TODO: Bootstrap can be imported here but does not register event handlers globally
//import * as bootstrap from 'bootstrap';

import {createApp} from 'vue';

import * as Bokeh from '@bokeh/bokehjs';
window.Bokeh = Bokeh;

import DeepZoomImage from '../components/DeepZoomImage.vue';

import Basket from './Basket.vue'
import SearchResults from './SearchResults.vue';

import 'topobank/scss/custom.scss';

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
export function createSearchResultsApp(el, csrfToken, props) {
    let app = createApp(SearchResults, props);
    app.provide('csrfToken', csrfToken);
    app.mount(el);
    return app;
}

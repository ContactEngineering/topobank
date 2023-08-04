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
 * Event bus for initiating DZI download
 */
import mitt from 'mitt';

const eventHub = mitt();

/**
 * Return event hub
 */
export function getEventHub() {
    return eventHub;
}

/**
 * Wrapper for an OpenSeadragon instance (with a scale bar)
 */
export function createDeepZoomImage(el, csrfToken, props) {
    let app = createApp(DeepZoomImage, props);
    app.provide('csrfToken', csrfToken);
    app.provide('eventHub', eventHub);
    app.mount(el);
    return app;
}

/**
 * Used to display search results/list of digital surface twins
 */
export function createSearchResultsApp(el, csrfToken, props) {
    let app = createApp(SearchResults, props);
    app.provide('csrfToken', csrfToken);
    app.provide('eventHub', eventHub);
    app.mount(el);
    return app;
}

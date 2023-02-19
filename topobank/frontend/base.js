import {createApp} from 'vue';
import Basket from './Basket.vue'

/**
 * Used to display "basket" on top if screen for all selected items in session
 *
 */
export function create_basket(el, event_hub, props) {
    let app = createApp(Basket, props);
    app.provide('event_hub', event_hub);
    app.mount(el);
    return app;
}

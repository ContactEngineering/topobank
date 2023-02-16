import Basket from './Basket.vue'

/**
 * Used to display "basket" on top if screen for all selected items in session
 *
 */
function make_basket(initial_basket_items) {
    return createApp(Basket).mount('#basket');
}

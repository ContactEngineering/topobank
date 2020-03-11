/**
 * Used to display "basket" on top if screen for all selected items in session
 *
 */
//
// var basket = new Vue({
//   delimiters: ['[[', ']]'],
//   el: '#basket',
//   data: {
//       keys: [],
//       elements: {} // key: key like "surface-1", value is object, see below
//   },
//   methods:{
//       get_element: function (key) {
//         return this.elements[key];
//       },
//       update: function () {
//           var tree = get_tree(); /** TODO get elements from session */
//           var elements = {};
//           var keys = [];
//
//           tree.getSelectedNodes().forEach(function (node) {
//
//               // console.log("is selected: "+node.key);
//
//               if (node.type!="tag") { // TODO also push list of tags?
//
//                   var key = node.key;
//
//                   // Only add a new key if key is not yet in elements
//                   if (!(key in elements)) {
//                         // console.log("Added key " + key);
//                         elements[key] = {
//                             name: node.data.name,
//                             type: node.type,
//                             nodes: [node] // at least one node
//                         };
//                         keys.push(key);
//                   } else {
//                         // console.log("Key " + key + " already included in basket");
//                         elements[key].nodes.push(node); // maintain list of nodes where this key is used
//                   }
//                   // console.log("Current element: ", elements[key]);
//               }
//           });
//           // console.log("All elements before removal: ", elements);
//
//           // remove all elements which parent element is already included
//           var keys_to_remove = []
//           keys.forEach(function (key) {
//              var elem = elements[key];
//              var first_node_data = elem.nodes[0].data;
//              if (first_node_data.hasOwnProperty('surface_key') && (first_node_data.surface_key in elements)) {
//                  keys_to_remove.push(key);
//              }
//           });
//           keys_to_remove.forEach(function (key) {
//               delete elements[key];
//           });
//           keys = keys.filter( function (key) {
//              return keys_to_remove.indexOf(key) == -1
//           });
//           keys.sort() // we want always the same order, independent from traversal order
//
//           // console.log("All elements: ", elements);
//           this.elements = elements;
//           this.keys = keys;
//       }
//   }
// });



 function make_basket(initial_basket_items) {
    return new Vue({
        delimiters: ['[[', ']]'],
        el: '#basket',
        data: {
            keys: [],
            elements: {}, // key: key like "surface-1", value is object, see below
            unselect_handler: null,  // set by calling basket.set_unselect_handler
        },
        mounted: function () {
            this.update(initial_basket_items);
        },
        created: function () {
            event_hub.$on('unselect', this.unselect);
        },
        methods: {

            get_element: function (key) {
                return this.elements[key];
            },
            update: function (basket_items) {

                if (basket_items === undefined) {
                    console.debug("Using initial basket items for upate.");
                    basket_items = initial_basket_items;
                }

                var elements = {};
                var keys = [];

                basket_items.forEach(function (item) {
                    keys.push(item.key);
                    elements[item.key] = item;
                });

                // remove all elements which parent element is already included
                var keys_to_remove = []
                keys.forEach(function (key) {
                    var elem = elements[key];
                    if (elem.hasOwnProperty('surface_key') && (elem.surface_key in elements)) {
                        keys_to_remove.push(key);
                    }
                });
                keys_to_remove.forEach(function (key) {
                    delete elements[key];
                });
                keys = keys.filter(function (key) {
                    return keys_to_remove.indexOf(key) == -1
                });
                keys.sort() // we want always the same order, independent from traversal order

                // console.log("All elements: ", elements);
                this.elements = elements;
                this.keys = keys;
            },

            unselect: function (key) {
                if (this.unselect_handler) {
                    console.log(`Calling unselect handler for key ${key} from basket..`);
                    this.unselect_handler(key);
                } else {
                    console.warn("Unselect handler not set for basket, cannot call.")
                }
            }
        }
    });

 }


Vue.component('basket-element', {
    props: ['elem'], // object with keys: 'name', 'type'
    delimiters: ['[[', ']]'],
    template: `
           <span v-if="elem.type=='surface'" class="badge badge-pill badge-primary mr-1">[[ elem.name ]]
                <span class="fa fa-close" v-on:click="handle_close"></span>
           </span>
           <span v-else class="badge badge-pill badge-secondary mr-1">[[ elem.name ]]
                <span class="fa fa-close" v-on:click="handle_close"></span>
           </span>
         `,
    methods: {
        handle_close: function (event) {
            event_hub.$emit('unselect', this.elem.key);  // See basket's "created" where event handlers are defined
        }
    }
  });

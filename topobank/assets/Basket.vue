<script>

import BasketElement from './BasketElement.vue';

export default {
  name: 'basket',
  components: {
    BasketElement
  },
  props: {
    analysis_list_url: String,
    csrf_token: String,
    initial_basket_items: Object,
    manager_download_selection_url: String,
    manager_select_url: String
  },
  inject: ['event_hub'],
  data() {
    return {
      keys: [],
      elements: {}, // key: key like "surface-1", value is object, see below
      unselect_handler: null,  // set in order to define what to be called if an item is "closed"
      // - should be null or a function(key) where key is an element of "keys", e.g. 'surface-1'
      // - should be used e.g. to deselect items in a tree or reload a page after deselecting
    };
  },
  mounted: function () {
    this.update(this.initial_basket_items);
  },
  created: function () {
    this.event_hub.on('basket-unselect', this.unselect);
    this.event_hub.on('basket-update', this.update);
  },
  methods: {
    get_element: function (key) {
      return this.elements[key];
    },
    update: function (basket_items) {

      let elements = {};
      let keys = [];

      if (basket_items === undefined) {
        console.debug("Using initial basket items for upate.");
        basket_items = this.initial_basket_items;
      }

      basket_items.forEach(function (item) {
        keys.push(item.key);
        elements[item.key] = item;
      });
      keys.sort((key_a, key_b) => elements[key_a].label.toLowerCase() > elements[key_b].label.toLowerCase());
      // we want always the same order, independent from traversal order

      this.elements = elements;
      this.keys = keys;
    },

    unselect_all: function () {
      const basket = this;
      $.ajax({
        type: "POST",
        url: unselect_all_url,
        data: {
          csrfmiddlewaretoken: this.csrf_token
        },
        success: function (data, textStatus, xhr) {
          if (basket.unselect_handler) {
            console.log("keys to unselect: ", basket.keys);
            basket.keys.forEach(function (key) {
              basket.unselect_handler(key);
            });
          }
          basket.update(data);
        },
        error: function (xhr, textStatus, errorThrown) {
          console.error("Could not unselect: " + errorThrown + " " + xhr.status + " " + xhr.responseText);
        }
      });
    },

    unselect: function (key) {
      // First call unselect url for this element
      // then the additional handler if needed
      const elem = this.elements[key];
      const basket = this;
      $.ajax({
        type: "POST",
        url: elem.unselect_url,
        data: {
          csrfmiddlewaretoken: this.csrf_token
        },
        success: function (data, textStatus, xhr) {
          basket.update(data);
          if (basket.unselect_handler) {
            //console.log(`Calling unselect handler for key ${key} from basket..`);
            basket.unselect_handler(key);
          } else {
            //console.debug("Unselect handler not set for basket, doing nothing extra.");
          }
        },
        error: function (xhr, textStatus, errorThrown) {
          console.error("Could not unselect: " + errorThrown + " " + xhr.status + " " + xhr.responseText);
        }
      });
    }
  }
}

</script>

<template>
  <div v-if="keys.length">
    <basket-element v-for="key in keys" v-bind:elem="get_element(key)" v-bind:key="key"></basket-element>
    <a class="btn btn-sm btn-outline-success" href="{{ analysis_list_url }}">
      Analyze
    </a>
    <div class="btn-group btn-group-sm float-right" role="group" aria-label="Actions on current selection">
      <button class="btn btn-sm btn-outline-secondary" v-on:click="unselect_all" id="unselect-all">
        Clear selection
      </button>
      <a class="btn btn-sm btn-outline-secondary"
         href="{{ manager_download_selection_url }}"
         type="button"
         id="download-selection">
        Download selected datasets
      </a>
    </div>
  </div>
  <div class="m-1" v-else>No items selected yet. In order to select for <em>comparative studies</em>,
    please check individual items on the
    <a class="text-dark" href="{{ manager_select_url }}">datasets</a> tab.
  </div>
</template>

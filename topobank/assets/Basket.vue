<script>
export default {
  name: 'basket',
  delimiters: ['[[', ']]'],
  data: {
    keys: [],
    elements: {}, // key: key like "surface-1", value is object, see below
    unselect_handler: null,  // set in order to define what to be called if an item is "closed"
    // - should be null or a function(key) where key is an element of "keys", e.g. 'surface-1'
    // - should be used e.g. to deselect items in a tree or reload a page after deselecting
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

      let elements = {};
      let keys = [];

      if (basket_items === undefined) {
        console.debug("Using initial basket items for upate.");
        basket_items = initial_basket_items;
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
          csrfmiddlewaretoken: csrf_token
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
          csrfmiddlewaretoken: csrf_token
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

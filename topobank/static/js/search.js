
/**
 * Search bar capabilities and result display as tree
 */




/**
 * Basket: Display for selected items, but do not show topographies if related surface is also selected
 *
 * Additional functionality: On click on a badge the related item should be removed from selection.
 */

/**
 *  Using vue component for displaying selected items, show surfaces in a different way than topographies
 */

Vue.component('basket-element', {
    props: ['item'],
    delimiters: ['[[', ']]'],
    template: `
           <span v-if="item.key.startsWith('surface')" class="badge badge-pill badge-primary mr-1" v-on:click="handle_click">[[ item.name ]]</span>
           <span v-else class="badge badge-pill badge-secondary mr-1" v-on:click="handle_click">[[ item.name ]]</span>
         `,
    methods: {
        handle_click: function (item) {
            tree.uncheck(item); // TODO pass node here
        },
        is_surface: function (item) {
            console.log("is_surface? " + item);
            return item.key.startsWith("surface");
        }
    }
});



// function set_basket_items(basket, tree) {
//     basket.items = [];
//     tree.getCheckedNodes().forEach(function (id) {
//         var item = window.tree.getDataById(id);
//
//         // only push topography item if
//         // - it is a surface
//         // - or it is a topography and its surface is not already
//         //   included because all topographies of the surface are included
//         // console.log(item.name + " " + item.is_surface_selected);
//         if (!item.hasOwnProperty('is_surface_selected') || !item.is_surface_selected) {
//             basket.items.push(item);
//             console.log("Pushed: " + item.key + " " + item.name + " " + item.is_surface_selected);
//         } else {
//             console.log("Not pushed: " + item.key + " " + item.name + " " + item.is_surface_selected);
//         }
//     });
// }

      var tree = $('#tree').tree({
          uiLibrary: 'bootstrap4',
          primaryKey: 'key',
          textField: 'name',
          childrenField: 'topographies',
          checkboxes: true,
          checkedField: 'is_selected',
          cascadeCheck: true, // enable cascade check and uncheck of children
          dataSource: "{% url 'manager:surface-search' %}",
          // imageUrlField: 'flagUrl'
          // TODO add filters to REST call
      });


      tree.on('checkboxChange', function (e, $node, item, state) {
          // console.log('Node '+ $node +': The new state of record ' + record.name + '(pk' + record.pk +' ) ' + ' is *' + state+'*');

          if (state == 'checked') {

              $.ajax({
                  type: "POST",
                  url: item.select_url,
                  data: {
                      csrfmiddlewaretoken: "{{csrf_token}}"
                  },
                  success: function (data, textStatus, xhr) {
                      // TODO make selection visible
                      console.log("Selected: "+item.name+" "+item.key+" "+item.is_selected);
                      //console.log(basket.items);
                      //console.log(item.is_surface_selected);
                      //if (    (basket.items.indexOf(item) == -1) // only push topography item if surface is not included
                      //     && ((!item.hasOwnProperty('is_surface_selected') || !item.is_surface_selected))) {
                      //   basket.items.push(item);
                      //}


                  },
                  error: function (xhr, textStatus, errorThrown) {
                      console.error("Could not select: " + errorThrown + " " + xhr.status + " " + xhr.responseText);
                  }
              });

          } else if ((state == 'unchecked') || (state == 'intermediate')) {

              $.ajax({
                  type: "POST",
                  url: item.unselect_url,
                  data: {
                      csrfmiddlewaretoken: "{{csrf_token}}"
                  },
                  success: function (data, textStatus, xhr) {
                      // TODO make selection invisible
                      console.log("Unselected: "+item.name+" "+item.key+" "+item.is_selected);
                      //var index = basket.items.indexOf(item);
                      //if (index > -1) {
                      //   basket.items.splice(index, 1);
                      //}
                  },
                  error: function (xhr, textStatus, errorThrown) {
                      console.error("Could not unselect: " + errorThrown + " " + xhr.status + " " + xhr.responseText);
                  }
              });

          }
          // set_basket_items();
      });

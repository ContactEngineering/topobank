

// See https://vuejs.org/v2/examples/select2.html as example how to wrap 3rd party code into a component

let search_results_vm = new Vue({
        delimiters: ['[[', ']]'],
        el: '#search-results',
        data: {
            tree_element: '#surface-tree',
            num_items: null,
            num_pages: null,
            page_range: null,
            page_urls: null,
            current_page: null,
            num_items_on_current_page: null,
            prev_page_url: null,
            next_page_url: null,
            search_url: null,

            element_kinds: {
                "surface list": "surfaces",
                "tag tree": "top level tags",
                "unknown": "(?)"
            },
            tree_mode: "surface list",
            hints: {
                "surface list": "The selected items are used when switching to analyses.",
                "tag tree": "Tags can be introduced or changed when editing meta data of surfaces and topographies.",
                "unknown": ""
            }
        },

        mounted: function() {
            var vm = this;
            $(vm.tree_element)
                // init fancytree
                .fancytree({
                  extensions: ["glyph", "table"],
                  glyph: {
                      preset: "awesome4",
                      map: {
                        // Override distinct default icons here
                        folder: "fa-folder",
                        folderOpen: "fa-folder-open"
                      }
                  },
                  types: {
                    "surface": {icon: "fa fa-diamond fa-fw", iconTooltip: "This is a surface"},
                    "topography": {icon: "fa fa-file-o fa-fw", iconTooltip: "This is a topography"},
                    "tag": {icon: "fa fa-tag fa-fw", iconTooltip: "This is a tag"},
                  },
                  icon: function(event, data) {
                    // data.typeInfo contains tree.types[node.type] (or {} if not found)
                    // Here we will return the specific icon for that type, or `undefined` if
                    // not type info is defined (in this case a default icon is displayed).
                    return data.typeInfo.icon;
                  },
                  iconTooltip: function(event, data) {
                     return data.typeInfo.iconTooltip; // set tooltip which appears when hovering an icon
                  },
                  table: {
                        checkboxColumnIdx: null,    // render the checkboxes into the this column index (default: nodeColumnIdx)
                        indentation: 20,         // indent every node level by these number of pixels
                        nodeColumnIdx: 0         // render node expander, icon, and title to this column (default: #0)
                    },
                  autoActivate: true,
                  titlesTabbable: false,
                  tabindex: -1,
                  focusOnSelect: false,
                  scrollParent: $("#scrollParent"),
                  checkbox: true,
                  selectMode: 3, // 'multi-hier'
                  // source: [], // will be replaced later
                  source: {
                    url: search_url,
                  },
                  postProcess: function(event, data) {
                    // assuming the Ajax response contains a list of child nodes:
                    console.log("PostProcess: ", data);
                    //console.log("vm in post process: ", vm);
                    // We replace the result
                    //vm.total_num_items = data.response.count;
                    //vm.prev_page_search_url = data.response.previous;
                    //vm.next_page_search_url = data.response.next;


                    //console.log("vm.prev_page_search_url: ", vm.prev_page_search_url);
                    //console.log("vm.next_page_search_url: ", vm.next_page_search_url);

                    vm.num_pages = data.response.num_pages;
                    vm.num_items = data.response.num_items;
                    vm.next_page_url = data.response.next_page_url;
                    vm.prev_page_url = data.response.prev_page_url;
                    vm.current_page = data.response.current_page;
                    vm.num_items_on_current_page = data.response.num_items_on_current_page;
                    vm.page_range = data.response.page_range;
                    vm.page_urls = data.response.page_urls;
                    vm.search_url = data.options.source.url;
                    data.result = data.response.page_results;
                  },
                  select: function(event, data) {
                      var node = data.node;
                      var is_selected = node.isSelected();

                      if (node.data.urls !== undefined) {
                        if (is_selected) {
                           $.ajax({
                               type: "POST",
                               url: node.data.urls.select,
                               data: {
                                   csrfmiddlewaretoken: csrf_token
                               },
                               success: function (data, textStatus, xhr) {
                                   // console.log("Selected: " + node.data.name + " " + node.key);
                                   basket.update(data);
                               },
                               error: function (xhr, textStatus, errorThrown) {
                                   console.error("Could not select: " + errorThrown + " " + xhr.status + " " + xhr.responseText);
                               }
                           });
                        } else {
                          $.ajax({
                               type: "POST",
                               url: node.data.urls.unselect,
                               data: {
                                   csrfmiddlewaretoken: csrf_token
                               },
                               success: function (data, textStatus, xhr) {
                                   // console.log("Unselected: " + node.data.name + " " + node.key);
                                   basket.update(data);
                               },
                               error: function (xhr, textStatus, errorThrown) {
                                   console.error("Could not unselect: " + errorThrown + " " + xhr.status + " " + xhr.responseText);
                               }
                           });
                        }
                      } else {
                        console.log("No urls defined for node. Cannot pass selection to session.");
                        basket.update();
                      }
                  },


                  renderColumns: function(event, data) {
                      var node = data.node;
                      var $tdList = $(node.tr).find(">td");

                      /**
                        Add special css classes to nodes depending on type
                       */

                      var extra_classes = {
                          surface: [],
                          topography: [],
                          tag: ['font-italic']
                      };

                      extra_classes[node.type].forEach(function (c) {
                        node.addClass(c);
                      });


                      /**
                       * Render columns
                       */

                      // Index #0 is rendered by fancytree, but extended here by tags
                      if (node.data.tags !== undefined) {
                          var tag_html = [];
                          node.data.tags.forEach(function (tag) {
                              tag_html += "<span class='badge badge-success mr-1'>" + tag + "</span>"
                          });

                          // append tags to fancytree-title
                          $tdList.eq(0).find('.fancytree-title').after(tag_html);

                      }

                      // Set column with description
                      if (node.data.description !== undefined) {
                          var description_html = `<div class='description-column'>${node.data.description}</div>`
                          $tdList
                              .eq(1)
                              .html(description_html);
                      }


                      // Set columns with buttons:
                      if (node.type !== "tag") {
                          var actions_html = `
                            <div class="btn-group btn-group-sm" role="group" aria-label="Actions">
                             ${item_buttons(node.data.urls)}
                            </div>
                          `;
                          $tdList
                              .eq(2)
                              .html(actions_html);
                      }

                      // Static markup (more efficiently defined as html row template):
                      // $tdList.eq(3).html("<input type='input' value='" + "" + "'>");
                      // ...
                    },
                }); // fancytree()
        },   // mounted()
        methods: {
            load_next_page: function (){
                if (this.next_page_url != null) {
                    console.log("Loading next page from URL '" + this.next_page_url + "'..");
                    tree = $(this.tree_element).fancytree("getTree");
                    tree.setOption('source', {
                        url: this.next_page_url,
                        cache: false,
                    });
                }
            },
            load_prev_page: function (){
                if (this.prev_page_url != null) {
                    console.log("Loading previous page from URL '"+this.prev_page_url+"'..");
                    tree = $(this.tree_element).fancytree("getTree");
                    tree.setOption('source', {
                      url: this.prev_page_url,
                      cache: false,
                    });
                }

            },
            load_page: function(page_no){
                page_no = parseInt(page_no);

                if ( (page_no>=1) && (page_no<=this.page_range.length) ) {
                    const tree = $(this.tree_element).fancytree("getTree");
                    const page_url = this.page_urls[page_no-1];
                    console.log("Loading page "+page_no+" from "+page_url+"..");
                    tree.setOption('source', {
                      url: page_url,
                      cache: false,
                    });
                } else {
                    console.warn("Cannot load page "+page_no+", because the page number is invalid.")
                }
            },

        }
      });  // Vue

// let pagination_vm = new Vue({
//         delimiters: ['[[', ']]'],
//         el: '#pagination',
//         data: {
//           num_pages: 0,
//           current_page: null,
//           prev_url: null,
//           next_url: null,
//         },
//         created: function() {
//
//         },
//         computed: {
//             has_prev: function() {
//                 return this.prev_url != null;
//             },
//             has_next: function() {
//                 return this.next_url != null;
//             },
//         },
//         methods: {
//
//         }
//       });

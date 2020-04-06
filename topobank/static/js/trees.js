

// See https://vuejs.org/v2/examples/select2.html as example how to wrap 3rd party code into a component

var surface_tree_vm = new Vue({
        delimiters: ['[[', ']]'],
        el: '#surface-tree',
        data: {
            total_num_items: 0,
            prev_page_search_url: null,
            next_page_search_url: null,
        },

        mounted: function() {
            var vm = this;
            $(this.$el)
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
                    vm.total_num_items = data.response.count;
                    vm.prev_page_search_url = data.response.previous;
                    vm.next_page_search_url = data.response.next;

                    console.log("vm.prev_page_search_url: ", vm.prev_page_search_url);
                    console.log("vm.next_page_search_url: ", vm.next_page_search_url);
                    data.result = data.response.results; // because of pagination, the results are underneath "results"
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

            vm.$on('prev_page_requested', function() {
                if (vm.prev_page_search_url != null) {
                    vm.load_prev_page();
                }
            });
            vm.$on('next_page_requested', function() {
                console.log("Got next signal");
                if (vm.next_page_search_url != null) {
                    vm.load_next_page();
                }
            });
        },   // mounted()
        methods: {
            load_next_page: function (event){
                if (this.next_page_search_url != null) {
                    console.log("Loading next page from URL '" + this.next_page_search_url + "'..");
                    tree = $(this.$el).fancytree("getTree");
                    tree.setOption('source', {
                        url: this.next_page_search_url,
                        cache: false,
                    });
                }
            },
            load_prev_page: function (event){
                if (this.prev_page_search_url != null) {
                    console.log("Loading previous page from URL '"+this.prev_page_search_url+"'..");
                    tree = $(this.$el).fancytree("getTree");
                    tree.setOption('source', {
                      url: this.prev_page_search_url,
                      cache: false,
                    });
                }

            }
        }
      });  // Vue

var pagination_vm = new Vue({
        delimiters: ['[[', ']]'],
        el: '#pagination',
        data: {
          num_pages: 0,
          prev_url: null,
          next_url: null,
        }
      });

/**
 * Compoment which represents the search result tree in the select page.
 * The tree is either in "surface list" mode or "tag tree" mode.
 *
 * "surface list" mode: Shows list of surfaces and their topographies underneath
 * "tag tree" mode: Shows tree of tags (multiple levels) and underneath the surfaces
 *                  and topographies tagged with the corresponding tags
 *
 * @type {Vue}
 *
 * See https://vuejs.org/v2/examples/select2.html as example how to wrap 3rd party code into a component
 */
let search_results_vm = new Vue({
        delimiters: ['[[', ']]'],
        el: '#search-results',
        data: {
            num_items: null,
            num_pages: null,
            page_range: null,
            page_urls: null,
            current_page: null,
            num_items_on_current_page: null,
            prev_page_url: null,
            next_page_url: null,
            base_search_urls: base_search_urls,
            search_term: search_term, // for filtering, comes from outside (search bar is on every page)
            category: null, // for filtering, will be set on page
            sharing_status: null, // will be set on page
            tree_element: "#surface-tree",
            tree_mode: "surface list",
            tree_mode_infos: {
                "surface list": {
                    element_kind: "surfaces",
                    hint: "The selected items are used when switching to analyses.",
                },
               "tag tree": {
                    element_kind: "top level tags",
                    hint: "Tags can be introduced or changed when editing meta data of surfaces and topographies.",
               }
            },
        },
        mounted: function() {
            const vm = this;
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
                  selectMode: 2, // 'multi'
                  source: {
                    url: this.search_url  // this is a computed property, see below
                  },
                  postProcess: function(event, data) {
                    console.log("PostProcess: ", data);
                    vm.num_pages = data.response.num_pages;
                    vm.num_items = data.response.num_items;
                    vm.next_page_url = data.response.next_page_url;
                    vm.prev_page_url = data.response.prev_page_url;
                    vm.current_page = data.response.current_page;
                    vm.num_items_on_current_page = data.response.num_items_on_current_page;
                    vm.page_range = data.response.page_range;
                    vm.page_urls = data.response.page_urls;
                    // assuming the Ajax response contains a list of child nodes:
                    // We replace the result
                    data.result = data.response.page_results;
                  },
                  select: function(event, data) {
                      const node = data.node;
                      const is_selected = node.isSelected();
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
                                   vm.set_selected_by_key(node.key, true);
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
                                   vm.set_selected_by_key(node.key, false);
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
                      const node = data.node;
                      const $tdList = $(node.tr).find(">td");

                      /**
                        Add special css classes to nodes depending on type
                       */

                      let extra_classes = {
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
                          let tag_html = [];
                          node.data.tags.forEach(function (tag) {
                              tag_html += "<span class='badge badge-success mr-1'>" + tag + "</span>"
                          });

                          // append tags to fancytree-title
                          $tdList.eq(0).find('.fancytree-title').after(tag_html);
                      }

                      // Set column with description
                      if (node.data.description !== undefined) {
                          const description_html = `<div class='description-column'>${node.data.description}</div>`
                          $tdList
                              .eq(1)
                              .html(description_html);
                      }


                      // Set columns with buttons:
                      if (node.type !== "tag") {
                          const actions_html = `
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
        computed: {
          search_url: function () {
              let url = this.base_search_urls[this.tree_mode];
              let query_strings = [];

              if ((this.search_term != null) && (this.search_term.length > 0)) {
                  query_strings.push("search="+this.search_term);
              }
              if ((this.category != null) && (this.category != 'all')) {
                  query_strings.push("category="+this.category);
              }
              if (this.sharing_status != null && (this.sharing_status != 'all')) {
                  query_strings.push("sharing_status="+this.sharing_status);
              }

              if (query_strings.length > 0) {
                  url += "?"+query_strings.join('&');
              }
              url = encodeURI(url)
              return url;
          }
        },
        methods: {
            get_tree: function() {
              return $(this.tree_element).fancytree("getTree");
            },
            reload: function(tree_mode, search_term, category, sharing_status) {
                const tree = this.get_tree();

                this.tree_mode = tree_mode;
                this.search_term = search_term;
                this.category = category;
                this.sharing_status = sharing_status;
                tree.reload({
                      url: this.search_url,
                      cache: false,
                });
            },
            load_page: function(page_no){
                page_no = parseInt(page_no);

                if ( (page_no>=1) && (page_no<=this.page_range.length) ) {
                    const tree = this.get_tree();
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
            set_selected_by_key: function(key, selected) {
                // Set selection on all nodes with given key and
                // set it to "selected" (bool)
                const tree = this.get_tree();
                tree.findAll( function (node) {
                    return node.key == key;
                }).forEach( function (node) {
                    node.setSelected(selected, {noEvents: true});
                    // we only want to set the checkbox here, we don't want to simulate the click
                })
            }

        }
      });  // Vue


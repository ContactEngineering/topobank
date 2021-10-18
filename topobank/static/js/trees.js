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
            num_items_on_current_page: null,
            base_urls: base_urls,
            current_page: initial_select_tab_state.current_page,
            page_size: initial_select_tab_state.page_size,
            search_term: initial_select_tab_state.search_term,
            category: initial_select_tab_state.category,
            sharing_status: initial_select_tab_state.sharing_status,
            tree_mode: initial_select_tab_state.tree_mode,
            tree_element: "#surface-tree",
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
            category_filter_choices: category_filter_choices,
            sharing_status_filter_choices: sharing_status_filter_choices,
            is_loading: false,
        },
        mounted: function() {
            const vm = this;
            $(vm.tree_element)
                // init fancytree
                .fancytree({
                  extensions: ["glyph", "table"],
                  glyph: {
                      preset: "awesome5",
                      map: {
                        // Override distinct default icons here
                        folder: "fa-folder",
                        folderOpen: "fa-folder-open"
                      }
                  },
                  types: {
                    "surface": {icon: "far fa-gem", iconTooltip: "This is a surface"},
                    "topography": {icon: "far fa-file", iconTooltip: "This is a measurement"},
                    "tag": {icon: "fas fa-tag", iconTooltip: "This is a tag"},
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
                  scrollParent: window,
                  autoScroll: true,
                  scrollOfs: {top: 200, bottom: 50},
                  checkbox: true,
                  selectMode: 2, // 'multi'
                  source: {
                     url: this.search_url.toString(),  // this is a computed property, see below
                     cache: false
                  },
                  postProcess: function(event, data) {
                    // console.log("PostProcess: ", data);
                    vm.num_pages = data.response.num_pages;
                    vm.num_items = data.response.num_items;
                    vm.current_page = data.response.current_page;
                    vm.num_items_on_current_page = data.response.num_items_on_current_page;
                    vm.page_range = data.response.page_range;
                    vm.page_urls = data.response.page_urls;
                    vm.page_size = data.response.page_size;
                    // assuming the Ajax response contains a list of child nodes:
                    // We replace the result
                    data.result = data.response.page_results;
                    vm.is_loading = false;
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

                      // Set column with number of measurements
                      if (node.data.topography_count !== undefined) {
                          let topo_count_html='<div class="text-right">'+node.data.topography_count+'</div>';
                          $tdList.eq(1).html(topo_count_html);
                      }

                      // Set columns with version and authors
                      if (node.data.version !== undefined) {
                          let version_html = node.data.version;
                          let authors_html = node.data.publication_authors;

                          if (node.data.publication_date.length > 0) {
                              version_html += " (" + node.data.publication_date +  ")";
                          }

                          version_html = "<div class='version-column'>" + version_html + "</div>";
                          $tdList
                              .eq(2)
                              .html(version_html);

                          // Also add badge for "published" to first column
                          if (node.data.version.toString().length > 0) {
                              published_html = "<span class='badge badge-info mr-1'>published</span>";
                              $tdList.eq(0).find('.fancytree-title').after(published_html);
                          }

                          $tdList
                              .eq(3)
                              .html(authors_html);

                      }

                      // Set column with description
                      if (node.data.description !== undefined) {
                          const descr = node.data.description;
                          const descr_id = "description-"+node.key;
                          const btn_id = descr_id+"-btn";
                          let first_nl_index = descr.indexOf("\n");  // -1 if no found

                          // console.log("Description: "+descr.substring(0,10)+" Key: "+node.key+" descr ID: "+descr_id+"\n");
                          let description_html = "<div class='description-column'>";
                          if (first_nl_index === -1) {
                              description_html += descr;
                          } else {
                              description_html += `
                                   <div>
                                        ${descr.substring(0, first_nl_index)}
                                        <button id="${btn_id}" href="#${descr_id}"
                                         class="btn btn-sm btn-default"
                                         data-toggle="collapse" data-target="#${descr_id}"
                                         data-text-collapsed="more" data-text-expanded="less">more</button>
                                   </div>
                                   <div id="${descr_id}" class="collapse">
                                        ${descr.substring(first_nl_index)}
                                   </div>
                              `;
                          }

                          description_html += "</div>";
                          $tdList
                              .eq(4)
                              .html(description_html);

                          $('#'+btn_id).on("click", function() {
                             var el = $(this);
                             if (el.text() === el.data("text-expanded")) {
                                 el.text(el.data("text-collapsed"));
                             } else {
                                 el.text(el.data("text-expanded"));
                             }
                          });
                      }

                      // Set columns with buttons:
                      if (node.type !== "tag") {
                          const actions_html = `
                            <div class="btn-group btn-group-sm" role="group" aria-label="Actions">
                             ${item_buttons(node.data.urls)}
                            </div>
                          `;
                          $tdList
                              .eq(5)
                              .html(actions_html);
                      }

                      // Static markup (more efficiently defined as html row template):
                      // $tdList.eq(3).html("<input type='input' value='" + "" + "'>");
                      // ...
                    },
                }); // fancytree()
                vm.set_loading_indicator();
        },   // mounted()
        computed: {
          search_url: function () {
              // Returns URL object

              let url = new URL(this.base_urls[this.tree_mode]);

              // replace page_size parameter
              // ref: https://usefulangle.com/post/81/javascript-change-url-parameters
              let query_params = url.searchParams;

              query_params.set("search", this.search_term);  // empty string -> no search
              query_params.set("category", this.category);
              query_params.set("sharing_status", this.sharing_status);
              query_params.set('page_size', this.page_size);
              query_params.set('page', this.current_page);
              query_params.set('tree_mode', this.tree_mode);
              url.search = query_params.toString();
              // url = url.toString();

              console.log("Requested search URL: "+url.toString());

              return url;
            },
        },
        methods: {
            get_tree: function() {
              return $(this.tree_element).fancytree("getTree");
            },
            set_loading_indicator: function() {
                // hack: replace loading indicator from fancytree by own indicator with spinner
                let loading_node = $('tr.fancytree-statusnode-loading');
                if (loading_node) {
                    loading_node.html(`
                        <td id="tree-loading-indicator" role="status">
                          <span id="tree-loading-spinner" class="spinner"></span>Please wait..
                        </td>
                    `);
                    this.is_loading = true;
                }
            },
            clear_search_term: function () {
                console.log("Clearing search term..");
                this.search_term = '';
                this.reload();
            },
            reload: function() {
                /*
                    Reload means: the tree must be completely reloaded,
                    with currently set state of the select tab,
                    except of the page number which should be 1.
                 */
                const tree = this.get_tree();
                this.current_page = 1;
                console.log("Reloading tree, tree mode: "+this.tree_mode+" current page: "+this.current_page);

                tree.setOption('source', {
                      url: this.search_url.toString(),
                      cache: false,
                });
                this.set_loading_indicator();
            },
            load_page: function(page_no){
                page_no = parseInt(page_no);

                if ( (page_no>=1) && (page_no<=this.page_range.length) ) {
                    let tree = this.get_tree();
                    let page_url=new URL(this.page_urls[page_no-1]);

                    console.log("Loading page "+page_no+" from "+page_url+"..");
                    tree.setOption('source', {
                      url: page_url,
                      cache: false,
                    });
                    this.set_loading_indicator();
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


<script>
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

export default {
  name: 'search-results',
  delimiters: ['[[', ']]'],
  props: {
    base_urls: Object,
    category_filter_choices: Object,
    csrf_token: String,
    current_page: Number,
    is_anonymous: Boolean,
    sharing_status_filter_choices: Object,
    search_term: String,
    surface_create_url: String,
    initial_category: Object,
    initial_is_loading: Boolean,
    initial_page_size: Number,
    initial_sharing_status: String,
    initial_tree_mode: String
  },
  data() {
    return {
      category: this.initial_category,
      is_loading: this.initial_is_loading,
      num_items: null,
      num_items_on_current_page: null,
      num_pages: null,
      page_range: null,
      page_size: this.initial_page_size,
      page_urls: null,
      sharing_status: this.initial_sharing_statuss,
      tree_element: "#surface-tree",
      tree_mode: this.initial_tree_mode,
      tree_mode_infos: {
        "surface list": {
          element_kind: "digital surface twins",
          hint: 'Analyze selected items by clicking on the "Analyze" button.',
        },
        "tag tree": {
          element_kind: "top level tags",
          hint: "Tags can be introduced or changed when editing meta data of surfaces and topographies.",
        }
      }
    }
  },
  mounted: function () {
    $(this.tree_element)
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
            "surface": {icon: "far fa-gem", iconTooltip: "This is a digital surface twin"},
            "topography": {icon: "far fa-file", iconTooltip: "This is a measurement"},
            "tag": {icon: "fas fa-tag", iconTooltip: "This is a tag"},
          },
          icon: function (event, data) {
            // data.typeInfo contains tree.types[node.type] (or {} if not found)
            // Here we will return the specific icon for that type, or `undefined` if
            // not type info is defined (in this case a default icon is displayed).
            return data.typeInfo.icon;
          },
          iconTooltip: function (event, data) {
            return data.typeInfo.iconTooltip; // set tooltip which appears when hovering an icon
          },
          table: {
            checkboxColumnIdx: null,    // render the checkboxes into the this column index (default: nodeColumnIdx)
            indentation: 20,            // indent every node level by these number of pixels
            nodeColumnIdx: 0            // render node expander, icon, and title to this column (default: #0)
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
          postProcess: function (event, data) {
            // console.log("PostProcess: ", data);
            this.num_pages = data.response.num_pages;
            this.num_items = data.response.num_items;
            this.current_page = data.response.current_page;
            this.num_items_on_current_page = data.response.num_items_on_current_page;
            this.page_range = data.response.page_range;
            this.page_urls = data.response.page_urls;
            this.page_size = data.response.page_size;
            // assuming the Ajax response contains a list of child nodes:
            // We replace the result
            data.result = data.response.page_results;
            this.is_loading = false;
          },
          select: function (event, data) {
            const node = data.node;
            const is_selected = node.isSelected();
            if (node.data.urls !== undefined) {
              if (is_selected) {
                $.ajax({
                  type: "POST",
                  url: node.data.urls.select,
                  data: {
                    csrfmiddlewaretoken: this.csrf_token
                  },
                  success: function (data, textStatus, xhr) {
                    // console.log("Selected: " + node.data.name + " " + node.key);
                    basket.update(data);
                    this.set_selected_by_key(node.key, true);
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
                    this.set_selected_by_key(node.key, false);
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

          renderTitle: function (event, data) {
            return " ";
          },

          renderColumns: function (event, data) {
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

            node.addClass('select-tree-item')

            extra_classes[node.type].forEach(function (c) {
              node.addClass(c);
            });

            let description_html = "";

            // License image
            if (node.data.publication_license) {
              description_html += `<img src="/static/images/cc/${node.data.publication_license}.svg" title="Dataset can be reused under the terms of a Creative Commons license." style="float:right">`;
            }

            // Tags
            if (node.data.category) {
              description_html += `<p class='badge badge-secondary mr-1'>${node.data.category_name}</p>`;
            }

            if (node.data.sharing_status == "own") {
              description_html += `<p class='badge badge-info mr-1'>Created by you</p>`;
            } else if (node.data.sharing_status == "shared") {
              description_html += `<p class='badge badge-info mr-1'>Shared by ${node.data.creator_name}</p>`;
            }

            if (node.data.tags !== undefined) {
              node.data.tags.forEach(function (tag) {
                description_html += "<p class='badge badge-success mr-1'>" + tag + "</p>";
              });
            }

            // Title
            description_html += `<p class="select-tree-title">${node.data.name}</p>`;

            publication_info = "";
            if (node.data.publication_authors) {
              publication_info += `${node.data.publication_authors} (published ${node.data.publication_date})`;
            } else {
              if (node.type == "surface") {
                publication_info += `This dataset is unpublished. It was initiated by ${node.data.creator_name}.`;
              }
            }

            if (publication_info) {
              description_html += `<p class="select-tree-authors">${publication_info}</p>`;
            }

            // Set column with description
            if (node.data.description !== undefined) {
              description_html += `<p class='select-tree-description'>${node.data.description}</p>`;
            }

            info_footer = "";
            if (node.data.topography_count && node.data.version) {
              info_footer += `This is version ${node.data.version} of this digital surface twin and contains ${node.data.topography_count} measurements.`
            } else if (node.data.version) {
              info_footer += `This is version ${node.data.version} of this digital surface twin.`
            } else if (node.data.topography_count) {
              info_footer += `This digital surface twin contains ${node.data.topography_count} measurements.`
            }
            if ((node.type == "topography") && (node.data.sharing_status != "published")) {
              info_footer += `Uploaded by ${node.data.creator_name}.`;
            }
            if (info_footer) {
              description_html += `<p class="select-tree-info">${info_footer}</p>`
            }

            $tdList
                .eq(1)
                .html(description_html);

            // Set columns with buttons:
            if (node.type !== "tag") {
              const actions_html = `
                            <div class="btn-group-vertical btn-group-sm" role="group" aria-label="Actions">
                             ${item_buttons(node.data.urls)}
                            </div>
                          `;
              $tdList
                  .eq(2)
                  .html(actions_html);
            }
          },
        }); // fancytree()
    this.set_loading_indicator();
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

      console.log("Requested search URL: " + url.toString());

      return url;
    },
  },
  methods: {
    get_tree: function () {
      return $(this.tree_element).fancytree("getTree");
    },
    set_loading_indicator: function () {
      // hack: replace loading indicator from fancytree by own indicator with spinner
      let loading_node = $('tr.fancytree-statusnode-loading');
      if (loading_node) {
        loading_node.html(`
                        <td id="tree-loading-indicator" role="status">
                          <div class="h6">
                            <span id="tree-loading-spinner" class="spinner"></span>Please wait...
                          </div>
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
    reload: function () {
      /*
                Reload means: the tree must be completely reloaded,
                with currently set state of the select tab,
                except of the page number which should be 1.
             */
      const tree = this.get_tree();
      this.current_page = 1;
      console.log("Reloading tree, tree mode: " + this.tree_mode + " current page: " + this.current_page);

      tree.setOption('source', {
        url: this.search_url.toString(),
        cache: false,
      });
      this.set_loading_indicator();
    },
    load_page: function (page_no) {
      page_no = parseInt(page_no);

      if ((page_no >= 1) && (page_no <= this.page_range.length)) {
        let tree = this.get_tree();
        let page_url = new URL(this.page_urls[page_no - 1]);

        console.log("Loading page " + page_no + " from " + page_url + "..");
        tree.setOption('source', {
          url: page_url,
          cache: false,
        });
        this.set_loading_indicator();
      } else {
        console.warn("Cannot load page " + page_no + ", because the page number is invalid.")
      }
    },
    set_selected_by_key: function (key, selected) {
      // Set selection on all nodes with given key and
      // set it to "selected" (bool)
      const tree = this.get_tree();
      tree.findAll(function (node) {
        return node.key == key;
      }).forEach(function (node) {
        node.setSelected(selected, {noEvents: true});
        // we only want to set the checkbox here, we don't want to simulate the click
      })
    }
  }
}
</script>

<template>
  <div>
    <form>
      <div class="form-row justify-content-around">

        <div v-if="search_term" class="form-group col-md-4">
          <button class="btn btn-warning form-control" type="button"
                  id="clear-search-term-btn"
                  @click="clear_search_term">
            Clear filter for <b>[[ search_term ]]</b>
          </button>
        </div>
        <div v-else class="form-group col-md-4">
          <button class="btn btn-outline-info form-control disabled" type="button">
            Not filtered for search term
          </button>
        </div>

        <div class="form-group col-md-2">
          <select name="category" class="form-control" v-model="category" @change="reload">
            <option v-for="(choice_label, choice_val) in category_filter_choices"
                    v-bind:value="choice_val" v-bind:selected="choice_val==category">
              [[ choice_label ]]
            </option>
          </select>
        </div>

        <div class="form-group col-md-2">
          <select name="sharing_status" class="form-control" v-model="sharing_status" @change="reload">
            <option v-for="(choice_label, choice_val) in sharing_status_filter_choices"
                    v-bind:value="choice_val" v-bind:selected="choice_val==sharing_status">
              [[ choice_label ]]
            </option>
          </select>
        </div>

        <div id="tree-selector" class="form-group btn-group btn-group-toggle">
          <label v-for="choice in
                     [ { label: 'Surface list',
                         value: 'surface list',
                         icon_class: 'far fa-gem'},
                       { label:'Tag tree',
                         value: 'tag tree',
                         icon_class: 'fas fa-tag'}]"
                 class="btn"
                 v-bind:class="{active: tree_mode==choice.value,
                                    'btn-success': tree_mode==choice.value,
                                    'btn-default': tree_mode!=choice.value}">
            <input type="radio" class="btn-group-toggle" autocomplete="off"
                   name="tree_mode"
                   v-bind:value="choice.value" v-model="tree_mode" @change="reload">
            <span><i v-bind:class="choice.icon_class"></i> [[ choice.label ]]</span>
          </label>
        </div>
      </div>
    </form>

    <div class="row">
      <div class="col-md-8">
        <nav aria-label="Pagination">
          <ul id="pagination" class="pagination">
            <li class="page-item" v-bind:class="{ disabled: current_page <= 1 }">
              <a class="page-link" v-on:click="load_page(current_page-1)">Previous</a>
            </li>
            <li class="page-item" v-bind:class="{ active: current_page==page_no}" v-for="page_no in page_range">
              <a class="page-link" v-on:click="load_page(page_no)">[[ page_no ]]</a>
            </li>
            <li class="page-item" v-bind:class="{ disabled: current_page >=num_pages }">
              <a class="page-link" v-on:click="load_page(current_page+1)">Next</a>
            </li>

            <li class="ml-2">
              <div class="input-group nav-item">
                <div class="input-group-prepend">
                  <label class="input-group-text" for="page-size-select">Page size</label>
                </div>
                <select name="page_size" class="custom-select" id="page-size-select" v-model="page_size"
                        @change="reload()">
                  <option v-for="ps in [10,25,50,100]" v-bind:class="{selected: ps==page_size}">[[ ps ]]</option>
                </select>
              </div>
            </li>
          </ul>
        </nav>
      </div>

      <div class="col-md-4">
        <div v-if="is_anonymous" class="form-group">
          <button class="btn btn-primary form-control disabled"
                  title="Please sign-in to use this feature">Create digital surface twin
          </button>
        </div>
        <div v-if="!is_anonymous" class="form-group" title="Create a new digital surface twin">
          <a class="btn btn-primary form-control" :href="surface_create_url">Create digital
            surface
            twin</a>
        </div>
      </div>
    </div>

    <div id="scrollParent">
      <table id="surface-tree" class="table table-condensed surface-tree">
        <!--
        <colgroup>
          <col width="150rem"></col>
          <col></col>
          <col width="100rem"></col>
        </colgroup>
        -->
        <thead>
        <tr>
          <th scope="col">Select</th>
          <th scope="col">Description</th>
          <th scope="col">Actions</th>
        </tr>
        </thead>
        <tbody>
        </tbody>
      </table>
    </div>
    <div>
      <span v-if="!is_loading">
        Showing [[ num_items_on_current_page ]] [[ tree_mode_infos[tree_mode].element_kind ]] out of [[ num_items ]].
        [[ tree_mode_infos[tree_mode].hint ]]
      </span>
    </div>
  </div>
</template>

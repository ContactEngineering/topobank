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

import $ from 'jquery';
import axios from "axios";

import {createTree} from 'jquery.fancytree';

import 'jquery.fancytree/dist/modules/jquery.fancytree.glyph';
import 'jquery.fancytree/dist/modules/jquery.fancytree.table';

import Basket from './Basket.vue';

export default {
    name: 'search-results',
    components: {
        Basket
    },
    inject: ['csrfToken'],
    props: {
        baseUrls: Object,
        category: String,
        categoryFilterChoices: Object,
        currentPage: Number,
        initialSelection: {
            type: Array,
            default: []
        },
        isAnonymous: Boolean,
        isLoading: Boolean,
        pageSize: Number,
        sharingStatus: String,
        sharingStatusFilterChoices: Object,
        searchTerm: String,
        treeMode: String
    },
    data() {
        return {
            _selection: this.initialSelection,
            _category: this.category,
            _currentPage: this.currentPage,
            _isLoading: this.isLoading,
            _numItems: null,
            _numItemsOnCurrentPage: null,
            _numPages: null,
            _pageRange: null,
            _pageSize: this.pageSize,
            _pageUrls: null,
            _searchTerm: this.searchTerm,
            _sharingStatus: this.sharingStatus,
            _tree: null,
            _treeMode: this.treeMode,
            _treeModeInfos: {
                "surface list": {
                    element_kind: "digital surface twins",
                    hint: 'Analyze selected items by clicking on the "Analyze" button.',
                },
                "tag tree": {
                    element_kind: "top level tags",
                    hint: "Tags can be introduced or changed when editing meta data of surfaces and topographies.",
                }
            }
        };
    },
    mounted() {
        // this is not accessible from the scope of the callback function of fancy tree
        const _this = this;

        // init fancytree
        this._tree = createTree('#surface-tree', {
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
                icon(event, data) {
                    // data.typeInfo contains tree.types[node.type] (or {} if not found)
                    // Here we will return the specific icon for that type, or `undefined` if
                    // not type info is defined (in this case a default icon is displayed).
                    return data.typeInfo.icon;
                },
                iconTooltip(event, data) {
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
                postProcess(event, data) {
                    // console.log("PostProcess: ", data);
                    _this._numPages = data.response.num_pages;
                    _this._numItems = data.response.num_items;
                    _this._currentPage = data.response.current_page;
                    _this._numItemsOnCurrentPage = data.response.num_items_on_currentPage;
                    _this._pageRange = data.response.page_range;
                    _this._pageUrls = data.response.page_urls;
                    _this._pageSize = data.response.page_size;
                    // assuming the Ajax response contains a list of child nodes:
                    // We replace the result
                    data.result = data.response.page_results;
                    _this._isLoading = false;
                },
                select(event, data) {
                    const node = data.node;
                    const is_selected = node.isSelected();
                    if (node.data.urls !== undefined) {
                        if (is_selected) {
                            fetch(node.data.urls.select, {method: 'POST', headers: {'X-CSRFToken': _this.csrfToken}})
                                .then(response => response.json())
                                .then(data => {
                                    _this._selection = data;
                                    _this.setSelectedByKey(node.key, true);
                                })
                                .catch(error => {
                                    console.error("Could not select: " + error);
                                });
                        } else {
                            fetch(node.data.urls.unselect, {method: 'POST', headers: {'X-CSRFToken': _this.csrfToken}})
                                .then(response => response.json())
                                .then(data => {
                                    _this._selection = data;
                                    _this.setSelectedByKey(node.key, false);
                                })
                                .catch(error => {
                                    console.error("Could not unselect: " + error);
                                });
                        }
                    } else {
                        console.log("No urls defined for node. Cannot pass selection to session.");
                    }
                },
                renderTitle(event, data) {
                    return " ";
                },
                renderColumns(event, data) {
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
                    // DOI badge added here
                    if (node.data.publication_doi) {
                        description_html += `<a class="badge bg-dark me-1 text-decoration-none" href="https://doi.org/${node.data.publication_doi}">${node.data.publication_doi}</a>`;
                    }
                    // License image
                    if (node.data.publication_license) {
                        description_html += `<img src="/static/images/cc/${node.data.publication_license}.svg" title="Dataset can be reused under the terms of a Creative Commons license." style="float:right">`;
                    }

                    // Tags
                    if (node.data.category) {
                        description_html += `<p class='badge bg-secondary me-1'>${node.data.category_name}</p>`;
                    }

                    if (node.data.sharing_status == "own") {
                        description_html += `<p class='badge bg-info me-1'>Created by you</p>`;
                    } else if (node.data.sharing_status == "shared") {
                        description_html += `<p class='badge bg-info me-1'>Shared by ${node.data.creator_name}</p>`;
                    }

                    if (node.data.tags !== undefined) {
                        node.data.tags.forEach(function (tag) {
                            description_html += "<p class='badge bg-success me-1'>" + tag + "</p>";
                        });
                    }

                    // Title
                    description_html += `<p class="select-tree-title">${node.data.name}</p>`;

                    let publication_info = "";
                    if (node.data.publication_authors) {
                        publication_info += `${node.data.publication_authors} (published ${node.data.publication_date})`;
                    } else {
                        if (node.type == "surface") {
                            publication_info += `This dataset is unpublished. It was created by ${node.data.creator_name}.`;
                        }
                    }

                    if (publication_info) {
                        description_html += `<p class="select-tree-authors">${publication_info}</p>`;
                    }

                    // Set column with description
                    if (node.data.description !== undefined) {
                        description_html += `<p class='select-tree-description'>${node.data.description}</p>`;
                    }

                    let info_footer = "";
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
            }
        ); // fancytree()
        this.setLoadingIndicator();
    },   // mounted()
    computed: {
        search_url() {
            // Returns URL object

            let url = new URL(this.baseUrls[this._treeMode]);

            // replace page_size parameter
            // ref: https://usefulangle.com/post/81/javascript-change-url-parameters
            let queryParams = url.searchParams;

            queryParams.set("search", this._searchTerm);  // empty string -> no search
            queryParams.set("category", this._category);
            queryParams.set("sharing_status", this._sharingStatus);
            queryParams.set('page_size', this._pageSize);
            queryParams.set('page', this._currentPage);
            queryParams.set('tree_mode', this._treeMode);
            url.search = queryParams.toString();
            // url = url.toString();

            console.log("Requested search URL: " + url.toString());

            return url;
        },
    },
    methods: {
        setLoadingIndicator() {
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
                this._isLoading = true;
            }
        },
        clearSearchTerm() {
            console.log("Clearing search term...");
            this._searchTerm = '';
            this.reload();
        },
        reload() {
            /* Reload means: the tree must be completely reloaded,
               with currently set state of the select tab,
               except of the page number which should be 1. */
            this._currentPage = 1;
            console.log("Reloading tree, tree mode: " + this._treeMode + " current page: " + this._currentPage);

            this._tree.setOption('source', {
                url: this.search_url.toString(),
                cache: false,
            });
            this.setLoadingIndicator();
        },
        loadPage(pageNo) {
            pageNo = parseInt(pageNo);

            if ((pageNo >= 1) && (pageNo <= this._pageRange.length)) {
                let page_url = new URL(this._pageUrls[pageNo - 1]);

                console.log("Loading page " + pageNo + " from " + page_url + "..");
                this._tree.setOption('source', {
                    url: page_url,
                    cache: false,
                });
                this.setLoadingIndicator();
            } else {
                console.warn("Cannot load page " + pageNo + ", because the page number is invalid.")
            }
        },
        setSelectedByKey(key, selected) {
            // Set selection on all nodes with given key and
            // set it to "selected" (bool)
            this._tree.findAll(function (node) {
                return node.key == key;
            }).forEach(function (node) {
                node.setSelected(selected, {noEvents: true});
                // we only want to set the checkbox here, we don't want to simulate the click
            })
        },
        setSelectedKeys(keys) {
            // Select on all nodes with key in `keys`
            console.log(this._tree);
            this._tree.visit(function (node) {
                node.setSelected(keys.includes(node.key), {noEvents: true});
            })
        },
        unselect(basket, keys) {
            this.setSelectedKeys(keys);
        },
        createSurface() {
            axios.post('/manager/api/surface/').then(response => {
               window.location.href = `/manager/html/surface/?surface=${response.data.id}`;
            });
        }
    }
}
</script>

<template>
    <basket :basket-items="_selection"
            @unselect-successful="unselect">
    </basket>
    <form>
        <div class="d-flex flex-row mb-2">
            <div v-if="_searchTerm" class="form-group flex-fill me-2">
                <button class="btn btn-warning form-control" type="button"
                        id="clear-search-term-btn"
                        @click="clearSearchTerm">
                    Clear filter for <b>{{ _searchTerm }}</b>
                </button>
            </div>
            <div v-else class="form-group flex-fill me-2">
                <button class="btn btn-outline-info form-control disabled" type="button">
                    Not filtered for search term
                </button>
            </div>

            <div class="form-group me-2">
                <select name="category" class="form-control" v-model="_category" @change="reload">
                    <option v-for="(choiceLabel, choiceVal) in categoryFilterChoices"
                            v-bind:value="choiceVal" v-bind:selected="choiceVal==_category">
                        {{ choiceLabel }}
                    </option>
                </select>
            </div>

            <div class="form-group me-2">
                <select name="sharing_status" class="form-control" v-model="_sharingStatus" @change="reload">
                    <option v-for="(choiceLabel, choiceVal) in sharingStatusFilterChoices"
                            v-bind:value="choiceVal" v-bind:selected="choiceVal==_sharingStatus">
                        {{ choiceLabel }}
                    </option>
                </select>
            </div>

            <div id="tree-selector" class="btn-group">
                <label v-for="choice in
                     [ { label: 'Surface list',
                         value: 'surface list',
                         icon_class: 'far fa-gem'},
                       { label:'Tag tree',
                         value: 'tag tree',
                         icon_class: 'fas fa-tag'}]"
                       v-bind:class="{active: _treeMode==choice.value,
                                    'btn': true,
                                    'btn-success': _treeMode==choice.value,
                                    'btn-outline-success': _treeMode!=choice.value}">
                    <input type="radio"
                           class="btn-check"
                           autocomplete="off"
                           name="tree_mode"
                           v-bind:value="choice.value" v-model="_treeMode" @change="reload">
                    <span><i v-bind:class="choice.icon_class"></i> {{ choice.label }}</span>
                </label>
            </div>
        </div>
    </form>

    <div class="row">
        <div class="col-md-8">
            <nav aria-label="Pagination">
                <ul id="pagination" class="pagination">
                    <li class="page-item" v-bind:class="{ disabled: _currentPage <= 1 }">
                        <a class="page-link" v-on:click="loadPage(_currentPage-1)">Previous</a>
                    </li>
                    <li class="page-item" v-bind:class="{ active: _currentPage==page_no}"
                        v-for="page_no in _pageRange">
                        <a class="page-link" v-on:click="loadPage(page_no)">{{ page_no }}</a>
                    </li>
                    <li class="page-item" v-bind:class="{ disabled: _currentPage >=_numPages }">
                        <a class="page-link" v-on:click="loadPage(_currentPage+1)">Next</a>
                    </li>

                    <li class="ms-2">
                        <div class="input-group nav-item">
                            <label class="input-group-text" for="page-size-select">Page size</label>
                            <select name="page_size" class="custom-select" id="page-size-select" v-model="_pageSize"
                                    @change="reload()">
                                <option v-for="ps in [10,25,50,100]" v-bind:class="{selected: ps==pageSize}">{{ ps }}
                                </option>
                            </select>
                        </div>
                    </li>
                </ul>
            </nav>
        </div>

        <div class="col-md-4">
            <div v-if="isAnonymous" class="form-group">
                <button class="btn btn-primary form-control disabled"
                        title="Please sign-in to use this feature"
                        disabled>
                    Create digital surface twin
                </button>
            </div>
            <div v-if="!isAnonymous" class="form-group" title="Create a new digital surface twin">
                <a class="btn btn-primary form-control"
                   @click="createSurface">
                    Create digital surface twin
                </a>
            </div>
        </div>
    </div>

    <div id="scrollParent">
        <table id="surface-tree" class="table table-condensed surface-tree">
            <colgroup>
                <col width="150rem">
                <col>
                <col width="100rem">
            </colgroup>
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
    <span v-if="!_isLoading">
      Showing {{ _numItemsOnCurrentPage }} {{ _treeModeInfos[_treeMode].element_kind }} out of {{ _numItems }}.
      {{ _treeModeInfos[_treeMode].hint }}
    </span>
    </div>
</template>

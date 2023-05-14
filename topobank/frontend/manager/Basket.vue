<script>

import BasketElement from './BasketElement.vue';

export default {
    name: 'basket',
    components: {
        BasketElement
    },
    props: {
        analysisListUrl: {
            type: String,
            default: '/analysis/html/list/'
        },
        csrfToken: String,
        basketItems: {
            type: Object,
            default: []
        },
        managerDownloadSelectionUrl: {
            type: String,
            default: '/manager/select/download'
        },
        managerSelectUrl: {
            type: String,
            default: '/manager/select'
        }
    },
    data() {
        return {
            _keys: [],
            _elements: {} // key: key like "surface-1", value is object, see below
        };
    },
    mounted() {
        this.update(this.basketItems);
    },
    methods: {
        update(basketItems) {
            let elements = {};
            let keys = [];

            if (basketItems === undefined) {
                console.debug("Using initial basket items for upate.");
                basketItems = this.basketItems;
            }

            basketItems.forEach(function (item) {
                keys.push(item.key);
                elements[item.key] = item;
            });
            keys.sort();
            // we want always the same order, independent of traversal order

            this._elements = elements;
            this._keys = keys;
        },
        unselect_all() {
            const _this = this;
            fetch(unselect_all_url, {method: 'POST', headers: {'X-CSRFToken': this.csrfToken}})
                .then(response => response.json())
                .then(data => {
                    console.log("keys to unselect: ", _this._keys);
                    _this._keys.forEach(function (key) {
                        _this.$emit('unselect-successful', key);
                    });
                    _this.update(data);
                })
                .catch(error => {
                    console.error("Could not unselect: " + error);
                });
        },
        unselect(key) {
            // First call unselect url for this element
            // then the additional handler if needed
            const elem = this._elements[key];
            const _this = this;
            fetch(elem.unselect_url, {method: 'POST', headers: {'X-CSRFToken': this.csrfToken}})
                .then(response => response.json())
                .then(data => {
                    _this.update(data);
                    _this.$emit('unselect-successful', key);
                })
                .catch(error => {
                    console.error("Could not unselect: " + error);
                });
        },
        analyze() {
            // Construct subjects dictionary
            let subjects = {}
            for (const [key, value] of Object.entries(this._elements)) {
                let [type, id] = key.split('-');
                id = Number(id);
                if (subjects[type] === undefined)
                    subjects[type] = [id];
                else
                    subjects[type].push(id);
            }
            // Encode to base64 for passing in URL
            let subjects_b64 = btoa(JSON.stringify(subjects));
            window.location.href = `${this.analysisListUrl}?subjects=${subjects_b64}`;
        }
    },
    watch: {
        basketItems(newValue, oldValue) {
            this.update(newValue);
        }
    }
}

</script>

<template>
    <div id="basket-container" class="container-fluid bg-light border rounded shadow-sm py-2 mb-5">
        <div v-if="_keys.length">
            <basket-element v-for="elem in _elements"
                            v-bind:elem="elem"
                            @unselect="unselect">
            </basket-element>
            <a class="btn btn-sm btn-outline-success" @click="analyze">
                Analyze
            </a>
            <div class="btn-group btn-group-sm float-right" role="group" aria-label="Actions on current selection">
                <button class="btn btn-sm btn-outline-secondary" v-on:click="unselect_all" id="unselect-all">
                    Clear selection
                </button>
                <a class="btn btn-sm btn-outline-secondary"
                   :href="managerDownloadSelectionUrl"
                   type="button"
                   id="download-selection">
                    Download selected datasets
                </a>
            </div>
        </div>
        <div class="m-1" v-else>No items selected yet. In order to select for comparative studies,
            please check individual items on the
            <a class="text-dark" href="{{ managerSelectUrl }}">datasets</a> tab.
        </div>
    </div>
</template>

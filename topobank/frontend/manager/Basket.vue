<script>

import BasketElement from './BasketElement.vue';

export default {
    name: 'basket',
    components: {
        BasketElement
    },
    inject: ['csrfToken'],
    props: {
        analysisListUrl: {
            type: String,
            default: '/analysis/html/list/'
        },
        apiUnselectAllUrl: {
            type: String,
            default: '/manager/api/selection/unselect-all/'
        },
        basketItems: {
            type: Object,
            default: []
        },
        hasAnalyzeButton: {
            type: Boolean,
            default: true
        },
        hasClearButton: {
            type: Boolean,
            default: true
        },
        hasDownloadButton: {
            type: Boolean,
            default: true
        },
        managerDownloadSelectionUrl: {
            type: String,
            default: '/manager/select/download'
        },
        managerSelectUrl: {
            type: String,
            default: '/manager/select'
        },
    },
    inject: ['csrfToken'],
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
        unselectAll() {
            const _this = this;
            fetch(this.apiUnselectAllUrl, {
                method: 'POST',
                headers: {'X-CSRFToken': this.csrfToken}
            })
                .then(response => response.json())
                .then(data => {
                    _this.update(data);
                    _this.$emit('unselect-successful', this, this._keys);
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
            fetch(elem.unselect_url, {
                method: 'POST',
                headers: {'X-CSRFToken': this.csrfToken}
            })
                .then(response => response.json())
                .then(data => {
                    _this.update(data);
                    _this.$emit('unselect-successful', _this, this._keys);
                })
                .catch(error => {
                    console.error("Could not unselect: " + error);
                });
        },
        getSubjects() {
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
            return subjects;
        },
        getSubjectsBase64() {
            return btoa(JSON.stringify(this.getSubjects()));
        },
        analyze() {
            // Encode to base64 for passing in URL
            window.location.href = `${this.analysisListUrl}?subjects=${this.getSubjectsBase64()}`;
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
    <div id="basket-container" class="container-fluid bg-light border rounded shadow-sm py-2 mb-2">
        <div v-if="_keys.length">
            <basket-element v-for="elem in _elements"
                            v-bind:elem="elem"
                            @unselect="unselect">
            </basket-element>
            <a v-if="hasAnalyzeButton"
               class="btn btn-sm btn-outline-success"
               @click="analyze">
                Analyze
            </a>
            <div v-if="hasClearButton || hasDownloadButton"
                 class="btn-group btn-group-sm float-end"
                 role="group"
                 aria-label="Actions on current selection">
                <button v-if="hasClearButton"
                        class="btn btn-sm btn-outline-secondary"
                        @click="unselectAll">
                    Clear selection
                </button>
                <a v-if="hasDownloadButton"
                   class="btn btn-sm btn-outline-secondary"
                   :href="managerDownloadSelectionUrl"
                   type="button">
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

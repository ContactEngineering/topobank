<script>

import BasketElement from './BasketElement.vue';

export default {
    name: 'basket',
    components: {
        BasketElement
    },
    props: {
        analysisListUrl: String,
        csrfToken: String,
        initialBasketItems: Object,
        managerDownloadSelectionUrl: String,
        managerSelectUrl: String
    },
    inject: ['eventHub'],
    data() {
        return {
            keys: [],
            elements: {} // key: key like "surface-1", value is object, see below
        };
    },
    created() {
        this.eventHub.on('basket-unselect', this.unselect);
        this.eventHub.on('basket-update', this.update);
    },
    mounted() {
        this.update(this.initialBasketItems);
    },
    methods: {
        get_element(key) {
            return this.elements[key];
        },
        update(basket_items) {
            let elements = {};
            let keys = [];

            if (basket_items === undefined) {
                console.debug("Using initial basket items for upate.");
                basket_items = this.initialBasketItems;
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

        unselect_all() {
            const _this = this;
            fetch(unselect_all_url, {method: 'POST', headers: {'X-CSRFToken': this.csrfToken}})
                .then(response => response.json())
                .then(data => {
                    console.log("keys to unselect: ", _this.keys);
                    _this.keys.forEach(function (key) {
                        _this.eventHub.emit('basket-unselect-successful', key);
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
            const elem = this.elements[key];
            const _this = this;
            fetch(elem.unselect_url, {method: 'POST', headers: {'X-CSRFToken': this.csrfToken}})
                .then(response => response.json())
                .then(data => {
                    _this.update(data);
                    _this.eventHub.emit('basket-unselect-successful', key);
                })
                .catch(error => {
                    console.error("Could not unselect: " + error);
                });
        },
        analyze() {
            // Construct subjects dictionary
            let subjects = {}
            for (const [key, value] of Object.entries(this.elements)) {
                let [type, id] = key.split('-');
                type = 'manager_' + type;
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
    }
}

</script>

<template>
    <div v-if="keys.length">
        <basket-element v-for="key in keys" v-bind:elem="get_element(key)" v-bind:key="key"></basket-element>
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
    <div class="m-1" v-else>No items selected yet. In order to select for <em>comparative studies</em>,
        please check individual items on the
        <a class="text-dark" href="{{ managerSelectUrl }}">datasets</a> tab.
    </div>
</template>

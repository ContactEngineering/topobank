<script>

import SeriesCard from './SeriesCard.vue';
import RoughnessParametersCard from 'topobank_statistics/RoughnessParametersCard.vue';
import ContactMechanicsCard from 'topobank_contact/ContactMechanicsCard.vue';
import Basket from "topobank/manager/Basket.vue";

export default {
    name: 'analysis-results-list',
    components: {
        Basket,
        SeriesCard,
        RoughnessParametersCard,
        ContactMechanicsCard
    },
    props: {
        apiRegistryUrl: {
            type: String,
            default: '/analysis/api/registry/'
        },
        csrfToken: String,
        subjects: String
    },
    data() {
        return {
            _cards: [],
            _visible: []
        }
    },
    mounted() {
        const _this = this;
        fetch(this.apiRegistryUrl, {method: 'GET', headers: {'X-CSRFToken': this.csrfToken}})
            .then(response => response.json())
            .then(data => {
                this._cards = data.map(function (v) {
                    let visible = _this.$cookies.get(`card-${v.id}`);
                    visible = visible === null ? false : visible === 'true';
                    return {...v, visible: visible}
                });
            });
    },
    computed: {
        subjectsAsBasketItems() {
            console.log(this.subjects);
            const subjects = JSON.parse(atob(this.subjects));
            let basket = [];
            for (const [key, value] of Object.entries(subjects)) {
                for (const id of value) {
                    basket.push({
                        key: `${key}-${id}`,
                        type: key,
                        id: id,
                        label: null
                    });
                }
            }
            return basket;
        },
        visibleCards() {
            return this._cards.filter(v => v.visible);
        }
    },
    methods: {
        updateCookie(event) {
            this.$cookies.set(`card-${event.target.value}`, event.target.checked);
        }
    }
};
</script>

<template>
    <basket :csrf-token="csrfToken"
            :basket-items="subjectsAsBasketItems">
    </basket>
    <div class="row">
        <div class="col-12 form-group">
            <div v-for="card in this._cards"
                 class="custom-control custom-checkbox custom-control-inline">
                <input v-model="card.visible"
                       type="checkbox"
                       class="custom-control-input"
                       name="functions"
                       :value="card.id"
                       :id="`id_functions_${card.id}`"
                       @click="updateCookie">
                <label class="custom-control-label"
                       :for="`id_functions_${card.id}`">
                    {{ card.name }}
                </label>
            </div>
            <small id="hint_id_functions" class="form-text text-muted">
                Select one or multiple analysis functions.
            </small>
        </div>
    </div>
    <div class="row">
        <div v-for="card in this._cards" :class="{ 'col-lg-6': true, 'mb-4': true, 'd-none': !card.visible }">
            <component :is="`${card.visualization_type}-card`"
                       :csrf-token="csrfToken"
                       :enlarged="false"
                       :function-id="card.id"
                       :function-name="card.name"
                       :subjects="subjects">
            </component>
        </div>
    </div>
</template>

<script>

import Basket from "topobank/manager/Basket.vue";
import AnalysisCards from 'config/analysis_cards';

export default {
    name: 'analysis-results-list',
    components: {
        Basket,
        ...AnalysisCards
    },
    props: {
        apiRegistryUrl: {
            type: String,
            default: '/analysis/api/registry/'
        },
        subjects: String
    },
    inject: ['csrfToken'],
    data() {
        return {
            _cards: [],
            _visible: []
        }
    },
    mounted() {
        const _this = this;
        fetch(this.apiRegistryUrl, {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
                'X-CSRFToken': this.csrfToken
            }
        })
            .then(response => response.json())
            .then(data => {
                this._cards = data.map(function (v) {
                    let visible = _this.$cookies.get(`card-${v.id}`);
                    visible = visible === null ? false : visible === 'true';
                    return {...v, isCurrentlyVisible: visible, isOrWasVisible: visible}
                });
            });
    },
    computed: {
        subjectsAsBasketItems() {
            let subjects = [];
            try {
              subjects = JSON.parse(atob(this.subjects));
            }
            catch(err) {
              // Ignore errors that occur while parsing the subjects line
              //console.log(`Error encountered while parsing subjects string: ${err}.`);
              console.log(err);
            }
            let basket = [];
            for (const [key, value] of Object.entries(subjects)) {
                for (const id of value) {
                    basket.push({
                        key: `${key}-${id}`,
                        type: key,
                        id: id,
                        label: null,
                        select_url: `/manager/api/selection/${key}/${id}/select/`,
                        unselect_url: `/manager/api/selection/${key}/${id}/unselect/`
                    });
                }
            }
            return basket;
        },
        visibleCards() {
            return this._cards.filter(v => v.isCurrentlyVisible);
        }
    },
    methods: {
        updateCookie(event) {
            this.$cookies.set(`card-${event.target.value}`, event.target.checked);
        },
        basketItemsChanged(basket, key) {
            basket.analyze();  // reload page
        },
        visibilityChanged(card) {
          card.isOrWasVisible = true;
        }
    }
};
</script>

<template>
    <basket :basket-items="subjectsAsBasketItems"
            :has-analyze-button="false"
            :has-clear-button="false"
            :has-download-button="false"
            @unselect-successful="basketItemsChanged">
    </basket>
    <div class="row">
        <div class="col-12 form-group">
            <div v-for="card in this._cards"
                 class="custom-control custom-checkbox custom-control-inline">
                <input v-model="card.isCurrentlyVisible"
                       v-on:change="visibilityChanged(card)"
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
        <div v-for="card in this._cards"
             :class="{ 'col-lg-6': true, 'mb-4': true, 'd-none': !card.isCurrentlyVisible }">
            <component v-if="card.isOrWasVisible"
                       :is="`${card.visualization_type}-card`"
                       :enlarged="false"
                       :function-id="card.id"
                       :function-name="card.name"
                       :subjects="subjects">
            </component>
        </div>
    </div>
</template>

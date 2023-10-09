<script>

import axios from "axios";

import {BForm, BFormCheckbox, BFormCheckboxGroup, BFormGroup} from "bootstrap-vue-next";

import Basket from "topobank/manager/Basket.vue";
import AnalysisCards from 'config/analysis_cards';


export default {
    name: 'analysis-results-list',
    components: {
        Basket,
        BForm,
        BFormCheckbox,
        BFormCheckboxGroup,
        BFormGroup,
        ...AnalysisCards
    },
    props: {
        apiRegistryUrl: {
            type: String,
            default: '/analysis/api/function/'
        },
        subjects: String
    },
    data() {
        return {
            _activeCards: new Set([]),  // Cards that are active, i.e. have data loaded
            _cards: [],
            _visibleCards: []  // Cards that are visible
        }
    },
    mounted() {
        const visibleCards = this.$cookies.get("topobank-visible-cards");
        this._visibleCards = visibleCards === null ? [] : visibleCards;
        this._activeCards = new Set(this._visibleCards);
        axios.get(this.apiRegistryUrl)
            .then(response => {
                this._cards = response.data;
            });
    },
    computed: {
        subjectsAsBasketItems() {
            let subjects = [];
            try {
                subjects = JSON.parse(atob(this.subjects));
            } catch (err) {
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
        }
    },
    methods: {
        updateSelection(event) {
            this.$cookies.set("topobank-visible-cards", this._visibleCards);
            for (const id of this._visibleCards) {
                this._activeCards.add(id);
            }
        },
        basketItemsChanged(basket, key) {
            basket.analyze();  // reload page
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
    <div class="row mb-2">
        <b-form class="col-12">
            <b-form-group>
                <b-form-checkbox-group v-model="_visibleCards">
                    <b-form-checkbox v-for="card in this._cards"
                                     :value="card.id"
                                     @change="updateSelection">
                        {{ card.name }}
                    </b-form-checkbox>
                </b-form-checkbox-group>
            </b-form-group>
        </b-form>
    </div>
    <div class="row">
        <div v-for="card in this._cards"
             :class="{ 'col-lg-6': true, 'mb-4': true, 'd-none': !_visibleCards.includes(card.id) }">
            <component v-if="_activeCards.has(card.id)"
                       :is="`${card.visualization_type}-card`"
                       :enlarged="false"
                       :function-id="card.id"
                       :function-name="card.name"
                       :subjects="subjects">
            </component>
        </div>
    </div>
</template>

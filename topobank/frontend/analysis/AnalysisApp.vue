<script>

import SeriesCard from './SeriesCard.vue';
import RoughnessParametersCard from 'topobank_statistics/RoughnessParametersCard.vue';
import ContactMechanicsCard from 'topobank_contact/ContactMechanicsCard.vue';

export default {
    name: 'analysis-app',
    components: {
        SeriesCard,
        RoughnessParametersCard,
        ContactMechanicsCard
    },
    props: {
        csrfToken: String,
        subjects: Object
    },
    data() {
        return {
            _cards: [],
            _visible: []
        }
    },
    mounted() {
        fetch('/analysis/registry', {method: 'GET', headers: {'X-CSRFToken': this.csrfToken}})
            .then(response => response.json())
            .then(data => {
                this._cards = data.map(function (v) {
                    return {...v, visible: false}
                });
            });
    },
    computed: {
        visibleCards() {
            return this._cards.filter(v => v.visible);
        }
    }
};
</script>

<template>
    <div class="row">
        <div class="col-12 form-group">
            <div v-for="card in this._cards"
                 class="custom-control custom-checkbox custom-control-inline">
                <input v-model="card.visible"
                       type="checkbox"
                       class="custom-control-input"
                       name="functions"
                       :value="card.id"
                       :id="`id_functions_${card.id}`">
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

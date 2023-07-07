<script>

import AnalysisCards from 'config/analysis_cards';

export default {
    name: 'analysis-results-detail',
    components: AnalysisCards,
    props: {
        csrfToken: String,
        functionId: Number,
        functionName: String,
        visualizationType: String,
        subjects: String
    },
    data() {
        return {
            _cards: [],
            _visible: []
        }
    }
};
</script>

<template>
    <div class="row">
        <div class="col-lg-12 mb-4">
            <component :is="`${visualizationType}-card`"
                       :csrf-token="csrfToken"
                       :enlarged="true"
                       :function-id="functionId"
                       :function-name="functionName"
                       :subjects="subjects">
            </component>
        </div>
    </div>
</template>

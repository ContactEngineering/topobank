<script>

import axios from "axios";

import {
    BAlert, BButton, BButtonGroup, BCard, BCardBody, BForm, BFormGroup, BFormInput, BFormSelect, BFormTags,
    BFormTextarea, BSpinner
} from 'bootstrap-vue-next';

export default {
    name: 'surface-properties',
    components: {
        BAlert,
        BButton,
        BButtonGroup,
        BCard,
        BCardBody,
        BForm,
        BFormGroup,
        BFormInput,
        BFormSelect,
        BFormTags,
        BFormTextarea,
        BSpinner
    },
    props: {
        category: String,
        description: String,
        name: String,
        permission: String,
        surfaceUrl: String,
        tags: Object
    },
    data() {
        return {
            _category: this.category,
            _description: this.description,
            _editing: false,
            _error: null,
            _name: this.name,
            _options: [
                {value: 'exp', text: 'Experimental data'},
                {value: 'sim', text: 'Simulated data'},
                {value: 'dum', text: 'Dummy data'},
            ],
            _savedDescription: this.description,
            _savedName: this.name,
            _saving: false,
            _tags: this.tags
        }
    },
    methods: {
        saveCard() {
            this._editing = false;
            this._saving = true;
            axios.patch(this.surfaceUrl, {
                name: this._name,
                description: this._description,
                category: this._category,
                tags: this._tags
            }).then(response => {
                this._error = null;
                this.$emit('surface-updated', response.data);
            }).catch(error => {
                this._error = error;
                this._name = this._savedName;
                this._description = this._saveDescription;
            }).finally(() => {
                this._saving = false;
            });
        }
    },
    computed: {
        isEditable() {
            return this.permission !== 'view';
        }
    }
};
</script>

<template>
    <b-card>
        <template #header>
            <h5 class="float-start">Properties</h5>
            <b-button-group v-if="!_editing && !_saving && isEditable"
                            class="float-end"
                            size="sm">
                <b-button variant="outline-secondary"
                          @click="_savedName = `${_name}`; _savedDescription = `${_description}`; _editing = true">
                    <i class="fa fa-pen"></i>
                </b-button>
            </b-button-group>
            <b-button-group v-if="_editing || _saving"
                            class="float-end"
                            size="sm">
                <b-button v-if="_editing"
                          variant="danger"
                          @click="_editing = false; _name = _savedName; _description = _savedDescription">
                    Discard
                </b-button>
                <b-button variant="success"
                          @click="saveCard">
                    <b-spinner small v-if="_saving"></b-spinner>
                    SAVE
                </b-button>
            </b-button-group>
        </template>
        <b-card-body>
            <b-alert :model-value="_error !== null"
                     variant="danger">
                {{ _error.message }}
            </b-alert>
            <b-form>
                <b-form-group id="input-group-name"
                              label="Name"
                              label-for="input-name"
                              description="A short, descriptive name for this digital surface twin">
                    <b-form-input id="input-name"
                                  v-model="_name"
                                  placeholder="Please enter a name here"
                                  :disabled="!_editing">
                    </b-form-input>
                </b-form-group>
                <b-form-group id="input-group-description"
                              label="Description"
                              label-for="input-description"
                              description="Arbitrary descriptive text, ideally including information on specimen preparation, measurement conditions, etc.">
                    <b-form-textarea id="input-description"
                                     v-model="_description"
                                     placeholder="Please enter a description here"
                                     rows="10"
                                     :disabled="!_editing">
                    </b-form-textarea>
                </b-form-group>
                <b-form-group id="input-group-category"
                              label="Category"
                              label-for="input-category"
                              description="Please indicate the category of the data contained in this digital surface twin.">
                    <b-form-select id="input-category"
                                   v-model="_category"
                                   :options="_options"
                                   :disabled="!_editing">
                    </b-form-select>
                </b-form-group>
                <b-form-group id="input-group-tags"
                              label="Tags"
                              label-for="input-tags"
                              description="Attach arbitrary tags (labels) to this digital surface twin. Tags can be hierachical (like a directory structure); separate hierarchies with a /, e.g. 'bear/foot/nail' may indicate a set of topography scans on the nail of a bear foot.">
                    <b-form-tags id="input-tags"
                                   v-model="_tags"
                                   :disabled="!_editing">
                    </b-form-tags>
                </b-form-group>
            </b-form>
        </b-card-body>
    </b-card>
</template>

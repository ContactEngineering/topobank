<script>

import axios from "axios";

import {
    BAlert, BButton, BButtonGroup, BCard, BCardBody, BForm, BFormSelect, BSpinner
} from 'bootstrap-vue-next';

export default {
    name: 'surface-permissions',
    components: {
        BAlert,
        BButton,
        BButtonGroup,
        BCard,
        BCardBody,
        BForm,
        BFormSelect,
        BSpinner
    },
    props: {
        surfaceUrl: String,
        permissions: Object,
    },
    data() {
        return {
            _editing: false,
            _error: null,
            _permissions: this.permissions,
            _savedPermissions: this.permissions,
            _saving: false,
            _options: [
                {value: 'view', text: 'Allowed to view this digital surface twin'},
                {value: 'edit', text: 'Can edit (add, remove, modify measurements)'},
                {value: 'full', text: 'Full access (including publishing and access control)'}
            ]
        }
    },
    methods: {
        saveCard() {
            this._editing = false;
            this._saving = true;
            axios.patch(this.surfaceUrl, {name: this._name, description: this._description}).then(response => {
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
    }
};
</script>

<template>
    <b-card>
        <template #header>
            <h5 class="float-start">Permissions</h5>
            <b-button-group v-if="!_editing && !_saving"
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
            <b-button-group v-if="_editing || _saving"
                            class="float-end me-2"
                            size="sm">
                <b-button v-if="_editing"
                          variant="outline-secondary">
                    Share
                </b-button>
            </b-button-group>
        </template>
        <b-card-body>
            <b-alert :model-value="_error !== null"
                     variant="danger">
                {{ _error }}
            </b-alert>
            <div v-for="[userUrl, perms] in Object.entries(_permissions)"
                 class="row">
                <div class="col-4 my-auto">
                    {{ perms.name }} ({{ perms.orcid }})
                </div>
                <div class="col-6">
                    <b-form>
                        <b-form-select v-model="perms.permission"
                                       :options="_options"
                                       :disabled="!_editing">
                        </b-form-select>
                    </b-form>
                </div>
                <div class="col-2">
                    <b-button variant="outline-danger"
                              class="float-end"
                              :disabled="!_editing">
                        Unshare
                    </b-button>
                </div>
            </div>
        </b-card-body>
    </b-card>
</template>

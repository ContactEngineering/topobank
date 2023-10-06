<script>

import axios from "axios";

import {
    BAlert, BButton, BButtonGroup, BCard, BCardBody, BForm, BFormSelect, BSpinner, BModal
} from 'bootstrap-vue-next';

import SearchUserModal from "../components/SearchUserModal.vue";

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
        BSpinner,
        SearchUserModal,
        BModal
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
            _searchUser: false,
            _options: [
                {value: 'no-access', text: 'Revoke access (unshare digital surface twin)'},
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
            axios.patch(`${this.surfaceUrl}set-permissions/`, this._permissions).then(response => {
                this._error = null;
                this.$emit('permissions-updated', response.data);
            }).catch(error => {
                this._error = error;
                this._permissions = this._savedPermissions;
            }).finally(() => {
                this._saving = false;
            });
        },
        addUser(user) {
            this._searchUser = false;
            this._permissions.push({user: user, permission: 'view'});
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
                          @click="_savedPermissions = JSON.parse(JSON.stringify(_permissions)); _editing = true">
                    <i class="fa fa-pen"></i>
                </b-button>
            </b-button-group>
            <b-button-group v-if="_editing || _saving"
                            class="float-end"
                            size="sm">
                <b-button v-if="_editing"
                          variant="danger"
                          @click="_editing = false; _permissions = _savedPermissions">
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
                          variant="outline-secondary"
                          @click="_searchUser = !_searchUser">
                    Add user (share dataset)
                </b-button>
            </b-button-group>
        </template>
        <b-card-body>
            <b-alert :model-value="_error !== null"
                     variant="danger">
                {{ _error }}
            </b-alert>
            <div v-for="permission in _permissions"
                 class="row mb-2">
                <div class="col-4 my-auto">
                    {{ permission.user.name }} ({{ permission.user.orcid }})
                </div>
                <div class="col-8">
                    <b-form>
                        <b-form-select v-model="permission.permission"
                                       :options="_options"
                                       :disabled="!_editing">
                        </b-form-select>
                    </b-form>
                </div>
            </div>
        </b-card-body>
    </b-card>
    <search-user-modal v-model="_searchUser"
                       :class="{ 'd-block': _searchUser }"
                       @user-selected="addUser">
    </search-user-modal>
</template>

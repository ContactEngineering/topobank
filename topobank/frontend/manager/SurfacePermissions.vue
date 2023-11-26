<script setup>

import axios from "axios";
import {ref} from "vue";

import {
    BAlert, BButton, BButtonGroup, BCard, BCardBody, BForm, BFormSelect, BSpinner
} from 'bootstrap-vue-next';

import SearchUserModal from "../components/SearchUserModal.vue";

const props = defineProps({
    surfaceUrl: String,
    permissions: Object
});

const emit = defineEmits([
    'updated:permissions'
]);

const _editing = ref(false);
const _error = ref(null);
const _permissions = ref(props.permissions);
const _savedPermissions = ref(props.permissions);
const _saving = ref(false);
const _searchUser = ref(false);
const _options = ref([
    {value: 'no-access', text: 'Revoke access (unshare digital surface twin)'},
    {value: 'view', text: 'Allowed to view this digital surface twin'},
    {value: 'edit', text: 'Can edit (add, remove, modify measurements)'},
    {value: 'full', text: 'Full access (including publishing and access control)'}
]);

function saveCard() {
    _editing.value = false;
    _saving.value = true;
    axios.patch(`${props.surfaceUrl}set-permissions/`, _permissions.value.other_users).then(response => {
        _error.value = null;
        emit('update:permissions', response.data);
    }).catch(error => {
        _error.value = error;
        _permissions.value = this._savedPermissions;
    }).finally(() => {
        _saving.value = false;
    });
}

function addUser(user) {
    _searchUser.value = false;
    _permissions.value.other_users.push({user: user, permission: 'view'});
}

</script>

<template>
    <b-card>
        <template #header>
            <h5 class="float-start">Permissions</h5>
            <b-button-group v-if="!_editing && !_saving && _permissions.current_user.permission === 'full'"
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
                {{ _error.message }}
            </b-alert>
            <div class="row mb-2">
                <div class="col-4 my-auto">
                    <b>{{ _permissions.current_user.user.name }}<br>({{ _permissions.current_user.user.orcid }})</b>
                </div>
                <div class="col-8">
                    <b-form>
                        <b-form-select v-model="_permissions.current_user.permission"
                                       :options="_options"
                                       disabled>
                        </b-form-select>
                    </b-form>
                </div>
            </div>
            <hr/>
            <div v-if="_permissions.other_users.length == 0">
                Only you can access this digital surface twin.
            </div>
            <div v-if="_permissions.other_users.length > 0" v-for="permission in _permissions.other_users"
                 class="row mb-2">
                <div class="col-4 my-auto">
                    {{ permission.user.name }}<br>({{ permission.user.orcid }})
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
                       @user-selected="addUser">
    </search-user-modal>
</template>

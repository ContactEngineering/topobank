<script>

import axios from "axios";

import {
    BButton, BButtonGroup, BForm, BFormGroup, BFormInput, BModal
} from 'bootstrap-vue-next';

export default {
    name: 'search-user-modal',
    components: {
        BButton,
        BButtonGroup,
        BForm,
        BFormGroup,
        BFormInput,
        BModal
    },
    props: {
        url: {
            type: String,
            default: '/users/api/user/'
        },
        maxResults: {
            type: Number,
            default: 5
        }
    },
    emits: [
        'user-selected'
    ],
    data() {
        return {
            _searchTerm: '',
            _searchResult: []
        }
    },
    methods: {
        searchUser(searchTerm) {
            axios.get(`${this.url}?name=${searchTerm}&max=${this.maxResults}`).then(response => {
                this._searchResult = response.data;
            });
        },
        selectUser(user) {
            this.$emit('user-selected', user);
        }
    },
    watch: {
        _searchTerm(newValue, oldValue) {
            this.searchUser(newValue);
        }
    }
};
</script>

<template>
    <b-modal title="Search user" ok-only ok-title="Close">
        <b-form>
            <b-form-group id="input-group-1"
                          label="Name"
                          label-for="input-1"
                          description="Search by full name of the user.">
                <b-form-input id="input-1"
                              v-model="_searchTerm"
                              type="text"
                              placeholder="Type to search..."
                              required>
                </b-form-input>
            </b-form-group>
        </b-form>
        <b-button-group vertical class="w-100">
            <b-button v-for="user in _searchResult"
                      variant="outline-secondary"
                      @click="selectUser(user)">
                {{ user.name }} ({{ user.orcid }})
            </b-button>
        </b-button-group>
    </b-modal>
</template>

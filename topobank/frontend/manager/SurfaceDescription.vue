<script>

import axios from "axios";

import {
    BButton, BButtonGroup, BCard, BCardBody, BForm, BFormGroup, BFormInput, BFormTextarea
} from 'bootstrap-vue-next';

export default {
    name: 'surface-description',
    components: {
        BButton,
        BButtonGroup,
        BCard,
        BCardBody,
        BForm,
        BFormGroup,
        BFormInput,
        BFormTextarea,
    },
    props: {
        apiUrl: String,
        name: String,
        description: String
    },
    data() {
        return {
            _name: this.name,
            _description: this.description
        }
    }
};
</script>

<template>
    <b-card>
        <template #header>
            <h5 class="float-start">Description</h5>
            <b-button-group class="float-end" size="sm">
                <b-button variant="outline-secondary">
                    <i class="fa fa-pen"></i>
                </b-button>
                <b-button variant="outline-secondary">
                    <i class="fa fa-trash"></i>
                </b-button>
            </b-button-group>
        </template>
        <b-card-body>
            <b-form>
                <b-form-group id="input-group-name"
                              label="Name"
                              label-for="input-name"
                              description="A short, descriptive name for this digital surface twin">
                    <b-form-input id="input-name"
                                  v-model="_name"
                                  placeholder="Please enter a name here"
                                  required>
                    </b-form-input>
                </b-form-group>
                <b-form-group id="input-group-description"
                              label="Description"
                              label-for="input-description"
                              description="Arbitrary descriptive text, ideally including information on specimen preparation, measurement conditions, etc.">
                    <b-form-textarea id="input-description"
                                     v-model="_description"
                                     placeholder="Please enter a description here"
                                     rows="10">
                    </b-form-textarea>
                </b-form-group>
            </b-form>
        </b-card-body>
    </b-card>
</template>

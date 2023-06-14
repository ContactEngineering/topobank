<script>
/**
 * Component representing one element in the basket.
 */

export default {
    name: 'basket-element',
    props: {
        apiUrl: {
            type: String,
            default: '/manager/api'
        },
        elem: Object // object with keys: 'name', 'type', 'id'; if 'name' is null, then it will query name
    },
    inject: ['csrfToken'],
    created() {
        if (this.elem.label === null) {
            // Fetch label if not provided
            this.elem.label = '...';
            fetch(`${this.apiUrl}/${this.elem.type}/${this.elem.id}/`, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                    'X-CSRFToken': this.csrfToken
                }
            })
                .then(response => response.json())
                .then(data => {
                    this.elem.label = data.name;
                });
        }
    },
    methods: {
        // the following method is called when the "x" symbol is clicked in a basket item
        handle_close(event) {
            this.$emit('unselect', this.elem.key);  // See basket's "created" where event handlers are defined
        }
    }
}
</script>

<template>
  <span v-if="elem.type=='surface'" class="badge rounded-pill bg-primary me-1 basket-element">
    <span class="far fa-gem"></span>
    {{ elem.label }}
    <span class="fas fa-times" v-on:click="handle_close"></span>
  </span>
    <span v-else-if="elem.type=='tag'" class="badge rounded-pill bg-info me-1 basket-element">
    <span class="fas fa-tag"></span>
    {{ elem.label }}
    <span class="fas fa-times" v-on:click="handle_close"></span>
  </span>
    <span v-else class="badge rounded-pill bg-secondary me-1 basket-element">
    <span class="far fa-file"></span>
    {{ elem.label }}
    <span class="fas fa-times" v-on:click="handle_close"></span>
  </span>
</template>

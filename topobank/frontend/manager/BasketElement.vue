<script>
/**
 * Component representing one element in the basket.
 */

export default {
  name: 'basket-element',
  props: {
    elem: Object // object with keys: 'name', 'type'
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
  <span v-if="elem.type=='surface'" class="badge badge-pill badge-primary mr-1 basket-element">
    <span class="far fa-gem"></span>
    {{ elem.label }}
    <span class="fas fa-times" v-on:click="handle_close"></span>
  </span>
  <span v-else-if="elem.type=='tag'" class="badge badge-pill badge-info mr-1 basket-element">
    <span class="fas fa-tag"></span>
    {{ elem.label }}
    <span class="fas fa-times" v-on:click="handle_close"></span>
  </span>
  <span v-else class="badge badge-pill badge-secondary mr-1 basket-element">
    <span class="far fa-file"></span>
    {{ elem.label }}
    <span class="fas fa-times" v-on:click="handle_close"></span>
  </span>
</template>

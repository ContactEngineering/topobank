<script>

import {v4 as uuid4} from 'uuid';

import TasksStatusModal from './TasksStatusModal.vue';

export default {
  name: 'tasks-button',
  components: {
    TasksStatusModal
  },
  props: {
    analyses: Object,
    csrfToken: String,
    uid: {
      type: String,
      default() {
        return uuid4();
      }
    }
  }
}

</script>

<template>
  <button class="btn btn-default btn-sm float-right"
          href="#"
          data-toggle="modal"
          :data-target="`#task-status-modal-${uid}`">
    Tasks
  </button>
  <tasks-status-modal
      :id="`task-status-modal-${uid}`"
      :analyses="analyses"
      :csrf-token="csrfToken">
  </tasks-status-modal>
</template>

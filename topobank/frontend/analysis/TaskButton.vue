<script>

import {v4 as uuid4} from 'uuid';

import TaskStatusModal from './TaskStatusModal.vue';

export default {
  name: 'task-button',
  components: {
    TaskStatusModal
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
  <task-status-modal
      :id="`task-status-modal-${uid}`"
      :analyses="analyses"
      :csrf-token="csrfToken">
  </task-status-modal>
</template>

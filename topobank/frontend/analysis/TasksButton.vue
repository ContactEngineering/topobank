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
  },
  data() {
    return {
      _anyTaskIsRunning: true  // We assume some task is running and get notified if this is not the case
    }
  },
  methods: {
    taskStatusChanged(anyTaskIsRunning) {
      this._anyTaskIsRunning = anyTaskIsRunning;
    }
  }
}

</script>

<template>
  <button class="btn btn-default btn-sm float-right"
          href="#"
          data-toggle="modal"
          :data-target="`#task-status-modal-${uid}`">
    <div v-if="_anyTaskIsRunning" class="spinner"></div>
    Tasks
  </button>
  <tasks-status-modal
      :id="`task-status-modal-${uid}`"
      :analyses="analyses"
      :csrf-token="csrfToken"
      @task-status-changed="taskStatusChanged">
  </tasks-status-modal>
</template>

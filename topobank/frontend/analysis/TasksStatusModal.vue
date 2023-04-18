{# Include this into cards in order to have a modal view with task information #}

<script>

import TaskStatusRow from "./TaskStatusRow.vue";

export default {
  name: 'tasks-status-modal',
  components: {
    TaskStatusRow
  },
  props: {
    analyses: {
      type: Object,
      default: []
    },
    csrfToken: String
  },
  data() {
    return {
      _analyses: this.analyses === undefined ? [] : this.analyses,
      _taskStatuses: this.analyses === undefined ? [] : this.getInitialTaskStatuses(this.analyses),
      _selectedAnalyses: []
    }
  },
  watch: {
    analyses: {
      handler(newValue, oldValue) {
        console.log('TasksStatusModal.watch.analyses -> ' + newValue + ', ' + oldValue);
        let anyTaskWasRunning = this._taskStatuses.some(v => v);
        this._analyses = newValue === undefined ? [] : newValue;
        this._taskStatuses = newValue === undefined ? [] : this.getInitialTaskStatuses(newValue);
        let anyTaskIsRunning = this._taskStatuses.some(v => v);
        if (anyTaskWasRunning != anyTaskIsRunning) {
          this.$emit('task-status-changed', anyTaskIsRunning);
        }
      }
    }
  },
  mounted() {
    let anyTaskIsRunning = this._taskStatuses.some(v => v);
    this.$emit('task-status-changed', anyTaskIsRunning);
  },
  methods: {
    getInitialTaskStatuses(analyses) {
      return analyses.map(a => a.task_state == 'pe' || a.task_state == 'st');
    },
    setTaskStatus(analysisIndex, taskIsRunning) {
      console.log('TaskStatusRow.setTaskStatus -> ' + analysisIndex + ', ' + taskIsRunning);
      let anyTaskWasRunning = this._taskStatuses.some(v => v);
      this._taskStatuses[analysisIndex] = taskIsRunning;
      let anyTaskIsRunning = this._taskStatuses.some(v => v);
      if (anyTaskWasRunning != anyTaskIsRunning) {
        this.$emit('task-status-changed', anyTaskIsRunning);
      }
    }
  }
};
</script>

<template>
  <div class="modal fade" tabindex="-1" role="dialog"
       aria-labelledby="statusesModalLabel"
       aria-hidden="true">
    <div class="modal-dialog modal-xl" role="document">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title" id="statusesModalLabel">Tasks</h5>
          <button class="close" type="button" data-dismiss="modal" aria-label="Close">
            <span aria-hidden="true">×</span>
          </button>
        </div>
        <div v-if="_analyses.length > 0" class="modal-body">
          <small>
            <table class="table table-hover task-table">
              <thead>
              <tr>
                <th scope="col" style="width:100px"></th>
                <th scope="col">Task description</th>
                <th scope="col" style="width:150px">Actions</th>
              </tr>
              </thead>
              <tbody>
                <task-status-row
                    v-for="(analysis, index) in _analyses"
                    :analysis="analysis"
                    :csrf-token="csrfToken"
                    @set-task-status="(taskIsRunning) => setTaskStatus(index, taskIsRunning)">
                </task-status-row>
              </tbody>
            </table>
          </small>
          <div v-if="_analyses.length == 0" class="alert alert-info">
            No analysis was triggered for this function and these subjects.
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" type="button" data-dismiss="modal">Close</button>
        </div>
      </div>
    </div>
  </div>
</template>

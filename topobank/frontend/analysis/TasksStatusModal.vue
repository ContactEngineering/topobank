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
      _selectedAnalyses: []
    }
  },
  mounted: function () {
    console.log(this._analyses);
  },
  watch: {
    analyses: {
      handler(newValue, oldValue) {
        this._analyses = newValue === undefined ? [] : newValue;
        console.log(this._analyses);
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
                <th scope="col" style="width:5rem"></th>
                <th scope="col">Task description</th>
                <th scope="col" style="width:7rem">Actions</th>
              </tr>
              </thead>
              <tbody>
                <task-status-row
                    v-for="analysis in _analyses"
                    :analysis="analysis"
                    :csrf-token="csrfToken">
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

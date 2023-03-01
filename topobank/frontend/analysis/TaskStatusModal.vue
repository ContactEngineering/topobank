{# Include this into cards in order to have a modal view with task information #}

<script>

export default {
  name: 'task-status-modal',
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
  methods: {
    renew(url, analysis_ids) {
      fetch(url, {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
          'X-CSRFToken': this.csrfToken
        },
        body: JSON.stringify({
          analysis_ids: analysis_ids
        })
      })
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
                <th scope="col"></th>
                <th scope="col">Task description</th>
                <th scope="col">Actions</th>
              </tr>
              </thead>
              <tbody>
              <tr v-for="analysis in _analyses">
                <td>
                  <div v-if="analysis.task_state == 'su'" class="btn btn-default bg-success disabled">
                    <i class="fa fa-check text-white"></i>
                  </div>
                  <div v-if="analysis.task_state == 'fa'" class="btn btn-default bg-failure disabled">
                    <i class="fa fa-xmark text-white"></i>
                  </div>
                  <div v-if="analysis.task_state == 'pe'" class="btn btn-default bg-info disabled">
                    <i class="fa fa-hourglass text-white"></i>
                  </div>
                  <div v-if="analysis.task_state == 'st'" class="btn btn-default bg-primary disabled">
                    <div class="spinner text-white"></div>
                  </div>
                </td>
                <td>
                  <p>
                    {{ analysis.function.name }} on {{ analysis.subject.type }}
                    <a :href="analysis.subject.urls.detail">
                      {{ analysis.subject.name }}
                    </a>
                    with parameters {{ analysis.kwargs }}
                  </p>
                  <p>
                    Task was created {{ analysis.creation_time }}, started running {{ analysis.start_time }}
                    and ran for {{ analysis.duration }} seconds.
                  </p>
                </td>
                <td>
                  <a @click="renew(analysis.urls.renew, [analysis.id])" class="btn btn-default">
                    Renew
                  </a>
                </td>
              </tr>
              </tbody>
            </table>
          </small>
          <div v-if="_analyses.length == 0" class="alert alert-info">
            No analysis triggered for this function and these subjects.
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" type="button" data-dismiss="modal">Close</button>
        </div>
      </div>
    </div>
  </div>
</template>

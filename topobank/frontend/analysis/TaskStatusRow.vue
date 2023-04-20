<script>

export default {
  name: 'task-status-row',
  emits: [
    'setTaskStatus'
  ],
  props: {
    analysis: Object,
    csrfToken: String,
    statusTimeout: {
      type: Number,
      default: 2000  // milliseconds
    }
  },
  data() {
    return {
      _analysis: this.analysis,
      _error: null
    }
  },
  mounted() {
    this.scheduleStatusCheck();
  },
  methods: {
    scheduleStatusCheck() {
      // Tasks are still pending or running if this status check is scheduled
      if (this._analysis !== undefined) {
        if (this._analysis.task_state == 'pe' || this._analysis.task_state == 'st') {
          this.$emit('setTaskStatus', true);
          setTimeout(this.checkStatus, this.statusTimeout);
        } else if (this._analysis.task_state == 'fa') {
          // This is failure. Query reason.
          console.log('failed!!');
          fetch(`${this._analysis.api.dataUrl}/result.json`, {
            method: 'GET',
            headers: {
              'Accept': 'application/json',
              'Content-Type': 'application/json',
              'X-CSRFToken': this.csrfToken
            }
          })
              .then(response => response.json())
              .then(result => {
                console.log(result);
              });
        } else {
          // Task seems to have finished or failed
          this.$emit('setTaskStatus', false);
        }
      } else {
        // Something is wrong - TODO: We should emit an error here
        this.$emit('setTaskStatus', false);
      }
    },
    checkStatus() {
      fetch(this._analysis.api.statusUrl, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
          'X-CSRFToken': this.csrfToken
        }
      })
          .then(response => response.json())
          .then(data => {
            this._analysis = data;
            this.scheduleStatusCheck();
          })
    },
    renew() {
      fetch(this._analysis.api.statusUrl, {
        method: 'PUT',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
          'X-CSRFToken': this.csrfToken
        }
      })
          .then(response => response.json())
          .then(data => {
            this._analysis = data;
            this.scheduleStatusCheck();
          })
    }
  }
};
</script>

<template>
  <tr>
    <td>
      <div v-if="_analysis.task_state == 'su'" class="btn btn-default bg-success disabled">
        <i class="fa fa-check text-white"></i>
      </div>
      <div v-if="_analysis.task_state == 'fa'" class="btn btn-default bg-danger disabled">
        <i class="fa fa-circle text-white"></i>
      </div>
      <div v-if="_analysis.task_state == 'pe' || _analysis.task_progress === null"
           class="btn btn-default bg-light disabled">
        <div class="spinner text-white"></div>
      </div>
      <div v-if="_analysis.task_state == 'st' && _analysis.task_progress !== null"
           class="btn btn-default bg-light disabled">
        {{ Math.round(_analysis.task_progress.percent) }} %
      </div>
    </td>
    <td>
      <p>
        Computation of analysis '{{ _analysis.function.name }}' on {{ _analysis.subject.type }}
        <a :href="_analysis.subject.urls.detail">
          {{ _analysis.subject.name }}
        </a>.
      </p>
      <p>
        Parameters: {{ _analysis.kwargs }}
      </p>
      <p v-if="_analysis.task_state == 'su'">
        This task was created on {{ new Date(_analysis.creation_time) }},
        started running {{ new Date(_analysis.start_time) }}
        and ran for {{ Math.round(_analysis.duration) }} seconds.
      </p>
      <p v-if="_analysis.task_state == 'fa'">
        This task was created on {{ new Date(_analysis.creation_time) }},
        started running {{ new Date(_analysis.start_time) }}
        but failed.
      </p>
      <p v-if="_analysis.task_state == 'pe'">
        This task was created on {{ new Date(_analysis.creation_time) }} and is currently waiting to be started.
      </p>
      <p v-if="_analysis.task_state == 'st'">
        This task was created on {{ new Date(_analysis.creation_time) }}, started {{ new Date(_analysis.start_time) }}
        and is currently running.
      </p>
    </td>
    <td>
      <a @click="renew" class="btn btn-default">
        Renew
      </a>
    </td>
  </tr>
</template>

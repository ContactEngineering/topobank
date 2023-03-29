<script>

export default {
  name: 'task-status-row',
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
      _analysis: this.analysis
    }
  },
  mounted() {
    this.scheduleStatusCheck();
  },
  methods: {
    scheduleStatusCheck() {
      if (this._analysis !== undefined) {
        if (this._analysis.task_state == 'pe' || this._analysis.task_state == 'st') {
          setTimeout(this.checkStatus, this.statusTimeout);
        }
      }
    },
    checkStatus() {
      fetch(this._analysis.urls.status, {
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
      fetch(this._analysis.urls.status, {
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
      <div v-if="_analysis.task_state == 'pe'" class="btn btn-default bg-light disabled">
        <div class="spinner text-white"></div>
      </div>
      <div v-if="_analysis.task_state == 'st'" class="btn btn-default bg-light disabled">
        {{ _analysis.task_progress.percent }} %
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

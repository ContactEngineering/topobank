<script>

function toPercent(x) {
  return Math.round(x * 100);
}

export default {
  name: 'task-status-row',
  props: {
    analysis: Object,
    csrfToken: String,
    statusTimeout: {
      type: Number,
      default: 5000  // milliseconds
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
            console.log(data);
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
          })
    }
  }
};
</script>

<template>
  <tr>
    <td>
      <div v-if="analysis.task_state == 'su'" class="btn btn-default bg-success disabled">
        <i class="fa fa-check text-white"></i>
      </div>
      <div v-if="analysis.task_state == 'fa'" class="btn btn-default bg-failure disabled">
        <i class="fa fa-xmark text-white"></i>
      </div>
      <div v-if="analysis.task_state == 'pe'" class="btn btn-default bg-light disabled">
        <div class="spinner text-white"></div>
      </div>
      <div v-if="analysis.task_state == 'st'" class="btn btn-default bg-light disabled">
        {{ toPercent(analysis.task_progress) }} %
      </div>
    </td>
    <td>
      <p>
        Computation of analysis '{{ analysis.function.name }}' on {{ analysis.subject.type }}
        <a :href="analysis.subject.urls.detail">
          {{ analysis.subject.name }}
        </a>.
      </p>
      <p>
        Parameters: {{ analysis.kwargs }}
      </p>
      <p v-if="analysis.task_state == 'su'">
        This task was created on {{ analysis.creation_time }}, started running {{ analysis.start_time }}
        and ran for {{ analysis.duration }} seconds.
      </p>
      <p v-if="analysis.task_state == 'fa'">
        This task was created on {{ analysis.creation_time }}, started running {{ analysis.start_time }}
        but failed.
      </p>
      <p v-if="analysis.task_state == 'pe'">
        This task was created on {{ analysis.creation_time }} and is currently waiting to be started.
      </p>
      <p v-if="analysis.task_state == 'st'">
        This task was created on {{ analysis.creation_time }}, started {{ analysis.start_time }}
        and is currently running.
      </p>
    </td>
    <td>
      <a @click="renew()" class="btn btn-default">
        Renew
      </a>
    </td>
  </tr>
</template>

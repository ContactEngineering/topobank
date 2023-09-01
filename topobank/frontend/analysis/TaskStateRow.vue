<script>

export default {
    name: 'task-state-row',
    emits: [
        'setTaskState'
    ],
    props: {
        analysis: Number,
        pollingInterval: {
            type: Number,
            default: 2000  // milliseconds
        }
    },
    inject: ['csrfToken'],
    data() {
        return {
            _analysis: null,
            _error: null,
        }
    },
    mounted() {
        this.scheduleStateCheck();
    },
    methods: {
        scheduleStateCheck() {
            // Tasks are still pending or running if this state check is scheduled
            if (this._analysis !== null) {
                if (this._analysis.task_state == 'pe' || this._analysis.task_state == 'st') {
                    setTimeout(this.checkState, this.pollingInterval);
                } else if (this._analysis.task_state == 'fa') {
                    // This is a failure. Query reason.
                    if (this._analysis.error === null) {
                        // The analysis function did not raise an exception itself. This means it acutally finished and
                        // we have a result.json, that should contain an error message.
                        fetch(`${this._analysis.api.dataUrl}/result.json`, {
                            method: 'GET',
                            headers: {
                                'Accept': 'application/json',
                                'X-CSRFToken': this.csrfToken
                            }
                        })
                            .then(response => response.json())
                            .then(result => {
                                this._error = result.message;
                            });
                    } else {
                        // The analysis function failed and we have an error message (Python exception).
                        this._error = this._analysis.error;
                    }
                }
            }
            else {
                // Check immediate as _analysis is null
                this.checkState();
            }
        },
        checkState() {
            let statusUrl = `/analysis/api/status/${this.analysis}/`;
            fetch(statusUrl, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                    'X-CSRFToken': this.csrfToken
                }
            })
                .then(response => response.json())
                .then(data => {
                    if (this._analysis === null || this._analysis.task_state !== data.task_state) {
                        // State has changed
                        this.$emit('setTaskState', data.task_state);
                    }
                    // Update current state of the analysis
                    this._analysis = data;
                    this.scheduleStateCheck();
                })
        },
        renew() {
            this._analysis.task_state = 'pe';
            this.$emit('setTaskState', 'pe');
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
                    this.scheduleStateCheck();
                })
        }
    }
};
</script>

<template>
    <tr>
        <td>
            <div v-if="_analysis !== null && _analysis.task_state == 'su'" class="btn btn-default bg-success disabled">
                <i class="fa fa-check text-white"></i>
            </div>
            <div v-if="_analysis !== null && _analysis.task_state == 'fa'" class="btn btn-default bg-danger disabled">
                <i class="fa fa-circle text-white"></i>
            </div>
            <div v-if="_analysis === null || _analysis.task_state == 'pe' || _analysis.task_progress === null"
                 class="btn btn-default bg-light disabled">
                <div class="spinner text-white"></div>
            </div>
            <div v-if="_analysis !== null && _analysis.task_state == 'st' && _analysis.task_progress !== null"
                 class="btn btn-default bg-light disabled">
                {{ Math.round(_analysis.task_progress.percent) }} %
            </div>
        </td>
        <td v-if="_analysis === null">
            <p>Fetching analysis status, please wait...</p>
        </td>
        <td v-if="_analysis !== null">
            <p>
                Computation of analysis <i>{{ _analysis.function.name }}</i> on {{ _analysis.subject.type }}
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
                but failed
                <span v-if="_error !== null">
            with message <i>{{ _error }}</i>
          </span>.
            </p>
            <p v-if="_analysis.task_state == 'pe'">
                This task was created on {{ new Date(_analysis.creation_time) }} and is currently waiting to be started.
            </p>
            <p v-if="_analysis.task_state == 'st'">
                This task was created on {{ new Date(_analysis.creation_time) }}, started
                {{ new Date(_analysis.start_time) }}
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

<script>

import axios from "axios";

export default {
    name: 'task-state-row',
    emits: [
        'setTaskState'
    ],
    props: {
        analysis: Object,
        pollingInterval: {
            type: Number,
            default: 2000  // milliseconds
        }
    },
    data() {
        return {
            _analysis: this.analysis,
            _error: null,
            _function: null,
            _subject: null
        }
    },
    mounted() {
        this.scheduleStateCheck();
    },
    methods: {
        scheduleStateCheck() {
            // Tasks are still pending or running if this state check is scheduled
            if (this._analysis !== null) {
                if (this._function === null) {
                    axios.get(this._analysis.function)
                        .then(response => {
                            this._function = response.data;
                        });
                }

                if (this._subject === null) {
                    const subject = this._analysis.subject;
                    const subjectUrl = subject.topography !== null ?
                        subject.topography : subject.surface !== null ?
                            subject.surface : subject.collection;
                    axios.get(subjectUrl)
                        .then(response => {
                            this._subject = response.data;
                        });
                }

                if (this._analysis.task_state == 'pe' || this._analysis.task_state == 'st') {
                    setTimeout(this.checkState, this.pollingInterval);
                } else if (this._analysis.task_state == 'fa') {
                    // This is a failure. Query reason.
                    if (this._analysis.error === null) {
                        // The analysis function did not raise an exception itself. This means it actually finished and
                        // we have a result.json, that should contain an error message.
                        axios.get(`${this._analysis.data_prefix}result.json`)
                            .then(response => {
                                this._error = response.data.message;
                            });
                    } else {
                        // The analysis function failed and we have an error message (Python exception).
                        this._error = this._analysis.error;
                    }
                }
            } else {
                // Check immediate as _analysis is null
                this.checkState();
            }
        },
        checkState() {
            axios.get(this._analysis.url)
                .then(response => {
                    if (this._analysis === null || this._analysis.task_state !== response.data.task_state) {
                        // State has changed
                        this.$emit('setTaskState', response.data.task_state);
                    }
                    // Update current state of the analysis
                    this._analysis = response.data;
                    this.scheduleStateCheck();
                })
        },
        renew() {
            this._analysis.task_state = 'pe';
            this.$emit('setTaskState', 'pe');
            axios.put(this._analysis.url)
                .then(response => {
                    this._analysis = response.data;
                    this.scheduleStateCheck();
                })
        }
    },
    computed: {
        analysisId() {
            return this._analysis === null ? -1 : this._analysis.url.split('/').slice(-2, -1)[0];
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
            <p v-if="_function === null">
                <div class="spinner"></div>
                Retrieving function information...
            </p>
            <p v-if="_function !== null">
                Function name: <i>{{ _function.name }}</i>
            </p>
            <p v-if="_subject === null">
                <div class="spinner"></div>
                Retrieving function information...
            </p>
            <p v-if="_subject !== null">
                Subject name: <i>{{ _subject.name }}</i>
            </p>
            <p>
                Parameters: <i>{{ _analysis.kwargs }}</i>
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
            with message: <i>{{ _error }}</i>
          </span>
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

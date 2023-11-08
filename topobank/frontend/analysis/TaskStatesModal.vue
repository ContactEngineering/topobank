{# Include this into cards in order to have a modal view with task information #}

<script>

import TaskStateRow from "./TaskStateRow.vue";

export default {
    name: 'task-states-modal',
    emits: [
        'taskStateChanged'
    ],
    components: {
        TaskStateRow
    },
    inject: ['csrfToken'],
    props: {
        analyses: {
            type: Object,
            default: []
        }
    },
    data() {
        return {
            _analyses: this.analyses === undefined ? [] : this.analyses,
            _taskStates: this.analyses === undefined ? [] : this.getInitialTaskStates(this.analyses),
            _selectedAnalyses: []
        }
    },
    watch: {
        analyses: {
            handler(newValue, oldValue) {
                this._analyses = newValue === undefined ? [] : newValue;
                this._taskStates = newValue === undefined ? [] : this.getInitialTaskStates(newValue);
                this.$emit('taskStateChanged', this._taskStates);
            }
        }
    },
    mounted() {
        this.$emit('taskStateChanged', this._taskStates);
    },
    methods: {
        getInitialTaskStates(analyses) {
            return analyses.map(a => a.task_state === undefined ? 'pe' : a.task_state);
        },
        setTaskState(analysisIndex, taskState) {
            this._taskStates[analysisIndex] = taskState;
            this.$emit('taskStateChanged', this._taskStates);
        }
    }
};
</script>

<template>
    <div class="modal fade" tabindex="-1" role="dialog"
         aria-labelledby="taskStatesModalLabel"
         aria-hidden="true">
        <div class="modal-dialog modal-xl" role="document">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="taskStatesModalLabel">Tasks</h5>
                    <button class="close" type="button" data-dismiss="modal" aria-label="Close">
                        <span aria-hidden="true">×</span>
                    </button>
                </div>
                <div class="modal-body">
                    <small v-if="_analyses.length > 0">
                        <table class="table table-hover task-table">
                            <thead>
                            <tr>
                                <th scope="col" style="width:100px"></th>
                                <th scope="col">Task description</th>
                                <th scope="col" style="width:150px">Actions</th>
                            </tr>
                            </thead>
                            <tbody>
                            <task-state-row
                                    v-for="(analysis, index) in _analyses"
                                    :analysis="analysis"
                                    @set-task-state="(taskState) => setTaskState(index, taskState)">
                            </task-state-row>
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

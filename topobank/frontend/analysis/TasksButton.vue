<script>

import {v4 as uuid4} from 'uuid';

import TaskStatesModal from './TaskStatesModal.vue';

// Count the number of unique entries in the array `arr`.
function countUniqueEntries(arr, requiredKeys) {
    let nbElements = {};
    // Count elements
    for (let value of arr) {
        if (nbElements[value] === undefined) {
            nbElements[value] = 1;
        } else {
            nbElements[value] += 1;
        }
    }
    // Make sure `requiredKeys` are present in the return object
    if (requiredKeys !== undefined) {
        for (let key of requiredKeys) {
            if (nbElements[key] === undefined) {
                nbElements[key] = 0;
            }
        }
    }
    return nbElements;
}

export default {
    name: 'tasks-button',
    emits: [
        'taskStateChanged'
    ],
    components: {
        TaskStatesModal
    },
    inject: ['csrfToken'],
    props: {
        analyses: Object,
        uid: {
            type: String,
            default() {
                return uuid4();
            }
        }
    },
    inject: ['csrfToken'],
    data() {
        return {
            _nbFailed: 0,
            _nbRunningOrPending: 0,
            _nbSuccess: 0,
        }
    },
    methods: {
        taskStateChanged(taskStates) {
            let nbStates = countUniqueEntries(taskStates, ['pe', 'st', 're', 'fa', 'su']);
            this._nbRunningOrPending = nbStates['pe'] + nbStates['st'] + nbStates['re'];
            this._nbSuccess = nbStates['su'];
            this._nbFailed = nbStates['fa'];
            this.$emit('taskStateChanged', this._nbRunningOrPending, this._nbSuccess, this._nbFailed);
        }
    }
}

</script>

<template>
    <button class="btn btn-default btn-sm float-end"
            href="#"
            data-toggle="modal"
            :data-target="`#task-states-modal-${uid}`">
        <span v-if="_nbRunningOrPending > 0" class="spinner"></span>
        Tasks
        <span v-if="_nbRunningOrPending > 0" class="badge bg-secondary ms-1">{{ _nbRunningOrPending }}</span>
        <span v-if="_nbSuccess > 0" class="badge bg-success ms-1">{{ _nbSuccess }}</span>
        <span v-if="_nbFailed > 0" class="badge bg-danger ms-1">{{ _nbFailed }}</span>
    </button>
    <task-states-modal
            :id="`task-states-modal-${uid}`"
            :analyses="analyses"
            @task-state-changed="taskStateChanged">
    </task-states-modal>
</template>

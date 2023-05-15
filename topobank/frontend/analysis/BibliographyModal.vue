<script>

import {v4 as uuid4} from 'uuid';

export default {
    name: 'bibliography-modal',
    props: {
        dois: {
            type: Object,
            default: []
        },
        uid: {
            type: String,
            default() {
                return uuid4();
            }
        }
    }
};
</script>

<template>
    <div class="modal fade"
         tabindex="-1"
         role="dialog"
         :aria-labelledby="`dois-modal-label-${uid}`"
         aria-hidden="true">
        <div class="modal-dialog modal-xl" role="document">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title"
                        :id="`dois-modal-label-${uid}`">
                        Bibliography
                    </h5>
                    <button class="close" type="button" data-dismiss="modal" aria-label="Close">
                        <span aria-hidden="true">×</span>
                    </button>
                </div>
                <div v-if="dois.length > 0" class="modal-body">
                    This analysis used methods and algorithms described in the following publications:
                    <ul>
                        <li v-for="doi in dois">
                            <a :href="`https://doi.org/${doi}`" target="_blank">{{ doi }}</a>
                        </li>
                    </ul>
                </div>
                <div v-if="dois.length == 0" class="modal-body">
                    No bibliography related to these analyses was reported.
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" type="button" data-dismiss="modal">Close</button>
                </div>
            </div>
        </div>
    </div>
</template>

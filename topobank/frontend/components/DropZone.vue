<script>
/*
 * Inspired by https://www.smashingmagazine.com/2022/03/drag-drop-file-uploader-vuejs-3/
 */

function preventDefaults(e) {
    e.preventDefault();
}

export default {
    name: 'drop-zone',
    emits: [
        'files-dropped'
    ],
    data() {
        return {
            _active: false,
            _events: ['dragenter', 'dragover', 'dragleave', 'drop']
        }
    },
    mounted() {
        this._events.forEach((eventName) => {
            document.body.addEventListener(eventName, preventDefaults);
        });
    },
    unmounted() {
        this.events.forEach((eventName) => {
            document.body.removeEventListener(eventName, preventDefaults);
        })
    },
    methods: {
        onDrop(e) {
            this._active = false;
            this.$emit('files-dropped', [...e.dataTransfer.files]);
        }
    }
};

</script>

<template>
    <div class="drop-zone mb-1"
         :class="{ 'drop-zone-active': _active }"
         :data-active="_active"
         @dragenter.prevent="_active=true"
         @dragover.prevent="_active=true"
         @dragleave.prevent="_active=false"
         @drop.prevent="onDrop">
        <!-- share state with the scoped slot -->
        <slot :dropZoneActive="_active">Drop your measurements here</slot>
    </div>
</template>

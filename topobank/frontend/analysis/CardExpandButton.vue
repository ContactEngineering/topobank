<script>

export default {
    name: 'card-expand-button',
    props: {
        detailUrl: String,
        functionId: Number,
        subjects: String
    }
};
</script>

<template>
    <div class="btn-group btn-group-sm float-end">
        <a :href="`${detailUrl}${functionId}/?subjects=${subjects}`"
           class="btn btn-default float-end">
            <i class="fa fa-expand"></i>
        </a>
    </div>
</template>

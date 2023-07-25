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
    <div class="btn-group btn-group-sm float-right">
        <a :href="`${detailUrl}${functionId}/?subjects=${subjects}`"
           class="btn btn-default float-right">
            <i class="fa fa-expand"></i>
        </a>
    </div>
</template>

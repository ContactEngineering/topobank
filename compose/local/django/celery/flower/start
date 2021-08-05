#!/bin/sh

set -o errexit
set -o nounset


celery \
    --app=topobank.taskapp \
    --broker="${CELERY_BROKER_URL}" \
    flower --basic_auth="${CELERY_FLOWER_USER}:${CELERY_FLOWER_PASSWORD}"

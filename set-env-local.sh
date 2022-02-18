
# load some defaults from the settings for a local Docker stack;
# this is needed e.g. for the datacite settings for DOI creation
. .envs/.local/.django

export CELERY_BROKER_URL='amqp://roettger:secert7$@localhost:5672/topobank'
export FIREFOX_BINARY_PATH=`which firefox`
export GECKODRIVER_PATH=`which geckodriver`
export EMAIL_HOST=localhost
export EMAIL_PORT=8025



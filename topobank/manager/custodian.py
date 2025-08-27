import logging

from ..taskapp.celeryapp import app

_log = logging.getLogger(__name__)


@app.task
def periodic_cleanup():
    _log.info("Manager custodian called")

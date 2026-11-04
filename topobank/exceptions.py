class IncompleteMetadataError(Exception):
    """
    Raised when a data file is of a supported format and can be read, but does
    not contain the complete metadata (physical size, unit) required to process
    it, and the instance is configured (via `TOPOBANK_REJECT_INCOMPLETE_METADATA`)
    to reject such files instead of prompting the user to fill in the metadata.
    """

    pass


class TaskBackendError(Exception):
    """
    Raised to end a run that a task backend (see `TaskStateModel.task_backend`)
    reports as failed. `traceback` is the backend's own account of the failure,
    if it has one.
    """

    def __init__(self, message, traceback=None):
        super().__init__(message)
        self.traceback = None if traceback is None else str(traceback)

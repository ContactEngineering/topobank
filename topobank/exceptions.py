class IncompleteMetadataError(Exception):
    """
    Raised when a data file is of a supported format and can be read, but does
    not contain the complete metadata (physical size, unit) required to process
    it, and the instance is configured (via `TOPOBANK_REJECT_INCOMPLETE_METADATA`)
    to reject such files instead of prompting the user to fill in the metadata.
    """

    pass

Configuration
=============

DOI Generation
--------------
.. list-table:: DOI Generation
    :widths: 25 10 20 45
    :header-rows: 1

    * - ENV Variable
      - Type
      - Default
      - Description
    * - :code:`PUBLICATION_URL_PREFIX`
      - str
      - :code:`'https://contact.engineering/go/'`
      - Every publication has a unique *short url* which is calculated from the internal ID. This short url
        is appended to this URL. Together it's the URL which leads to the webpage in the app showing
        the published surface.
    * - :code:`PUBLICATION_DOI_MANDATORY`
      - bool
      - :code:`False`
      - If set to `True`, a publication fails if the DOI generation fails.
    * - :code:`PUBLICATION_DOI_PREFIX`
      - str
      - :code:`'99.999'` (invalid)
      - Must start with `10.`, use a prefix registered by you.
    * - :code:`DATACITE_USERNAME`
      - str
      - :code:`testuser`
      - User at DataCite which is allowed to register DOIs.
    * - :code:`DATACITE_PASSWORD`
      - str
      - :code:`testpassword`
      - Password of above user at DataCite.
    * - :code:`DATACITE_API_URL`
      - str
      - :code:`'https://api.test.datacite.org'`
      - URL of the API at DataCite. The default references an API for testing your setup. The real URL is
        `'https://api.datacite.org'`. Use that for real DOIs.
    * - :code:`PUBLICATION_DOI_STATE`
      - str
      - :code:`'draft'`
      - One of `'draft'`, `'registered'`, and `'findable'`. Only `'draft'` DOIs can be deleted, so change with care.
        Registered DOIs can be converted to findable DOIs later and vice versa. Findable DOIs are the state
        you finally want to real DOIs. The default value should be used for testing unless you know the
        DOIs are okay to be persistent.
    * - :code:`PUBLICATION_MAX_NUM_AUTHORS`
      - int
      - :code:`200`
      - Maximum number of authors per publication.
    * - :code:`PUBLICATION_MAX_NUM_AFFILIATIONS_PER_AUTHOR`
      - int
      - :code:`20`
      - Maximum number affiliations per author per publication.

Data import
-----------
.. list-table:: Data import
    :widths: 25 10 20 45
    :header-rows: 1

    * - ENV Variable
      - Type
      - Default
      - Description
    * - :code:`TOPOBANK_REJECT_INCOMPLETE_METADATA`
      - bool
      - :code:`False`
      - If set to `True`, uploaded files that are of a supported format and can be read, but
        that do not contain the metadata required to process them (physical size and unit), are
        rejected. The measurement's task fails with an explicit error stating that the format is
        supported but the metadata is incomplete, instead of leaving the measurement in a state
        that requires the user to fill in the missing metadata manually. Container/ZIP imports
        are not affected, because they carry this metadata in their ``index.json`` and populate
        it before the file is inspected.


Container / ZIP export
----------------------
.. list-table:: Container / ZIP export
    :widths: 25 10 20 45
    :header-rows: 1

    * - ENV Variable
      - Type
      - Default
      - Description
    * - :code:`TOPOBANK_SPOOL_MAX_SIZE`
      - int
      - :code:`67108864` (64 MB)
      - Maximum archive size in bytes kept in memory before spilling to disk during ZIP file creation.


File uploads
------------

Defaults for these live in :code:`topobank/settings/defaults.py`; a deployment
only defines the ones it wants to change.

.. list-table:: File uploads
    :widths: 25 10 20 45
    :header-rows: 1

    * - ENV Variable
      - Type
      - Default
      - Description
    * - :code:`TOPOBANK_UPLOAD_EXPIRE_SECONDS`
      - int
      - :code:`900`
      - Seconds a presigned upload POST stays valid.
    * - :code:`TOPOBANK_MAX_MEASUREMENT_UPLOAD_BYTES`
      - int
      - :code:`5368709120` (5 GiB)
      - Size ceiling for a measurement file, carried in the upload policy so storage enforces it.
        S3 refuses a single object above 5 GiB, so a larger value here would only promise what
        storage then rejects.
    * - :code:`TOPOBANK_MAX_ATTACHMENT_UPLOAD_BYTES`
      - int
      - :code:`104857600` (100 MiB)
      - Size ceiling for a single attachment, carried in the upload policy.
    * - :code:`TOPOBANK_MAX_ATTACHMENTS_PER_SURFACE`
      - int
      - :code:`200`
      - Maximum number of attachments a single dataset may hold. Bounds the unpaginated listing.
    * - :code:`TOPOBANK_OPAQUE_CONTENT_TYPE`
      - str
      - :code:`'binary/octet-stream'`
      - Content type stored for an attachment that is not previewable. Opaque on purpose: a bare
        presigned GET serves from the bucket origin, where an inline `.html` or `.svg` would be
        stored XSS. Measurement files are always stored opaquely and ignore this setting.
    * - :code:`TOPOBANK_INLINE_PREVIEW_TYPES`
      - dict
      - :code:`{'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif'}`
      - Attachment extensions a browser may render inline, mapped to the content type stored for
        them. The type is derived from the extension, never taken from the client. SVG stays out
        for the reason given above.

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







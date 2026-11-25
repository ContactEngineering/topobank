<!--
Style for this changelog (keep to it so entries stay uniform):

- Newest version first. Heading `vX.Y.Z (DDMonYY)`, underlined with dashes.
  A version not yet released is headed `vX.Y.Z (not yet released)`.
- One bullet per user-visible change, at most two lines (about 200
  characters). Say what changed for the user and, if useful, why or by how
  much. Omit internals: no function, class, file or variable names, no
  environment variables, no commit or PR references.
- Start every bullet with one of: `ENH:` (new feature), `BUG:` (fix),
  `API:` (interface change), `PERF:` (speed or memory), `SEC:` (security),
  `MAINT:`, `TST:`, `DOC:`, `BUILD:`, `CI:`.
- Small related fixes may share one bullet. No trailing period on bullets.
-->

Change log for TopoBank
=======================

v1.74.0 (24Nov26)
-----------------

- ENH: Deployments can hand workflows to their own dispatcher and run them outside Celery; without
  one, workflows go to Celery as before, and an invalid dispatcher fails Django's system checks
- ENH: A workflow run elsewhere can register output files it wrote straight into storage, without
  copying them; file names must be plain relative paths
- BUG: The dataset custodian skips measurements and datasets still referenced by protected records
  instead of aborting, so one such row no longer stops all soft-deleted datasets from being purged

v1.73.0 (14Oct26)
-----------------

- ENH: Thumbnails and deep zoom images can optionally be detrended beyond the measurement's own
  detrend mode, so a tilted scan no longer renders as a plain color gradient
- BUILD: Django 5.2.18
- CI: Runs on Ubuntu 26

v1.72.0 (10Sep26)
-----------------

- ENH: Measurements and attachments are uploaded directly to S3 via presigned POST, and storage
  enforces size (default 5 GiB for measurements, 100 MiB for attachments) and content type
- ENH: Every TopoBank setting has one central default, so a deployment defines only the settings it
  wants to change
- ENH: Attachments carry a user note, their size and their content type, which decides whether a
  browser displays them inline; all three are kept when a dataset is copied
- ENH: Uploaded attachments are confirmed by storage like measurement files, so a client that dies
  after uploading no longer leaves an orphaned file behind
- API: Presigned PUT uploads and the setting that selected them are removed
- API: The separate S3 on/off setting is removed; whether uploads can be presigned is now determined
  from the configured storage backend alone
- BUG: After small runs, the memory guard no longer refuses all later analyses of a workflow with
  TB-scale predictions; it discounts the process baseline and skips tiny subjects
- BUG: Deleting an analysis result without permissions, directly or through its measurement, no
  longer fails, and its folder and stored files are still removed
- ENH: The custodian fails analyses that were dispatched but are still pending after 7 days
  (configurable), since their task was lost and nothing else would ever move them
- ENH: Analysis results can be soft-deleted like datasets and measurements, and the custodian
  removes them for good once the retention window has closed
- ENH: Datasets and measurements record who soft-deleted them, so a recycle bin can show who deleted
  what while it is still recoverable
- TST: The full-text search index is covered by tests
- TST: Test users can be created without an ORCID iD, to test behaviour that depends on how a user
  signed in
- CI: S3 tests run against SeaweedFS instead of Minio, matching the development stack
- TST: The test settings are defined once; a duplicate copy had made the S3 test job run against
  local file storage and skip the direct-upload path
- BUILD: Dropped four unmaintained dependencies: backports.entry-points-selectable,
  dj-inmemorystorage, py and mergedeep
- BUILD: django-notifications-hq is pinned to a fixed commit, so a build no longer depends on the
  current state of its upstream default branch
- BUILD: Removed lower bounds on urllib3, lxml, jinja2, cryptography, Pillow, sqlparse and pyjwt
  that only guarded old CVEs; raised the django-allauth floor and dropped the Sphinx cap
- TST: The test settings honor the configured storage backend and upload method again, so the S3
  test job in CI actually runs against S3
- TST: A ZIP container test checks the requested spool size instead of breaking when the S3 storage
  backend also spools the files it reads
- DOC: Authentication, including ORCID sign-in, is documented in ce-ui; TopoBank's documentation
  only states that it needs a user model and, for social sign-in, a configured social app

v1.71.0 (03Aug26)
-----------------

- ENH: A data series records the extent of its data, so a plot can pick a suitable display unit
  without reading the series back from the object store
- ENH: Measurements record the trend removed by detrending: the slope of the removed tilt and the
  radius of the removed curvature, in physical units
- ENH: Measurements record the fraction of measured data that carries no value
- ENH: The custodian and a new management command fail tasks whose worker disappeared instead of
  leaving them running forever
- ENH: Analyses predicted to exceed the configured memory budget fail with an explanatory message
  instead of being killed by the OOM killer
- BUILD: Test fixtures are included in the wheel again without a workaround that added them twice
  and broke the build
- BUG: The undefined-data flag again describes the measured data; enabling filling of undefined data
  had erased it
- TST: Both topography test factories build measurements in the success state, which can be
  overridden

v1.70.1 (02Aug26)
-----------------

- BUG: Analyses no longer all fail once two workers register the same dependency version
  concurrently; PostgreSQL never enforced the uniqueness check for ordinary version numbers
- MAINT: Dependency version uniqueness is enforced by the database (requires PostgreSQL 15+); a
  migration merges existing duplicates
- MAINT: Looking up a package version tolerates duplicates left behind by older databases instead of
  failing the task

v1.70.0 (02Aug26)
-----------------

- ENH: Full-text search index
- ENH: Asynchronous creation of ZIP archives for downloads
- ENH: ZIP export accepts an archive name and opaque extra metadata
- ENH: ZIP containers are built in a spooled temporary file of configurable size
- BUG: Deleting a ZIP container no longer fails when its permission set is missing
- MAINT: Thumbnails of line scans are rendered with matplotlib's object-oriented API
- MAINT: New helper for displaying physical sizes in natural length units
- MAINT: Removed an inert changelog option from the notification command of the mock-auth test app

v1.69.4 (25Jul26)
-----------------

- MAINT: Fixed performance issue in migrations

v1.69.3 (24Jul26)
-----------------

- ENH: Workflow task time limits are taken from Celery's soft and hard time limit settings, with a
  6-hour hard limit by default
- ENH: Per-stage task timing is also saved when a workflow fails, so a timeout shows which stage
  used up the time budget

v1.69.2 (22Jul26)
-----------------

- PERF: Memory tracking records the peak memory of each task instead of tracing allocations, which
  slowed numpy-heavy tasks about 35x; allocation tracing is opt-in
- BUG: Memory tracing is stopped when a task raises, instead of staying enabled for all later tasks
  in the same worker process

v1.69.1 (21Jul26)
-----------------

- BUG: Analysis workers no longer build subject URLs, and alerts no longer require one

v1.69.0 (20Jul26)
-----------------

- ENH: Option to reject files with incomplete metadata
- ENH: Dataset containers use a single validated JSON metadata file
- ENH: Container ZIP export accepts optional opaque extra metadata
- ENH: Submitting analyses for datasets can ignore existing results
- ENH: Logical Celery queue names can optionally be remapped at publish time
- MAINT: Containers no longer include the legacy YAML metadata file, which is still read on import
- MAINT: New delete delay settings
- MAINT: Dataset names can be up to 255 characters long
- MAINT: Celery tasks of dependencies record which parent workflow they belong to
- MAINT: Admin pages for datasets and measurements select related objects by ID
- BUILD: Updated Django to 5.2.16
- BUG: A parent workflow fails when a dependency fails and keeps the dependency's traceback
- BUG: Concurrent submissions no longer create duplicate results
- BUG: Concurrent analyses no longer create duplicate configuration records
- BUG: The pending task state is saved when only selected measurement fields are updated
- BUG: Submitting returns the usable analysis, not simply the latest one
- BUG: Analyses of sets of datasets are invalidated and cleaned up
- BUG: Fixed a workflow crash related to timing; timing is now recorded per workflow
- BUG: Fixed lookup of existing analyses by their parameters

v1.68.0 (15Jun26)
-----------------

- ENH: Metadata can be passed when submitting an analysis
- ENH: Output schema for workflows
- ENH: JSON encoding supports pydantic models
- ENH: Timing of tasks
- MAINT: More task state information in list responses
- MAINT: Faster resolution of Celery task states
- MAINT: Available organization plugins are stored as a list of choices instead of a string
- MAINT: Plugin logic is handled dynamically
- MAINT: Fixed permissions for the workflow view
- MAINT: Removed a redundant serializer field source
- MAINT: Removed the usage statistics app
- MAINT: Deprecated the results dictionary
- MAINT: Separated dependency resolution and task execution
- MAINT: Simplified workflow serializers
- MAINT: JSON is saved with the extended JSON encoder
- MAINT: Better detection of whether the service is running within a Celery task
- MAINT: Performance and indexing optimizations
- MAINT: Improved transaction handling and atomic request settings
- MAINT: New setting for running behind PgBouncer
- MAINT: muFFT no longer exists and has been folded into muGrid
- BUILD: Updated Django to 5.2.10
- BUILD: Updated Sphinx dependency
- MAINT: Workflows are identified by name through the workflow registry instead of a database table
- MAINT: The subject of an analysis is stored directly with the result instead of in a separate
  dispatch table
- MAINT: Removed workflow templates
- MAINT: The anonymous user is optional; views fall back to it only when a deployment configures one
- BUG: Fixed app filter
- BUG: Fixed outputs schema
- BUG: Looking up a workflow whose implementation does not exist returns nothing
- BUG: Users can access the statistics backend; fixed the landing page
- TST: Tests use built-in mock apps for users, organizations and authorization instead of depending
  on topobank-orcid
- TST: Fixed test to reflect that tracebacks are now passed up from dependencies
- TST: Replaced deprecated pytz with Python's built-in zoneinfo in tests

v1.67.0 (16Dec25)
-----------------

- ENH: Generate NetCDF tile pyramid

v1.66.3 (07Feb26)
-----------------

- BUG: Workflows run directly after upload, without waiting for a readiness check
- BUG: Whether a measurement's file record exists is checked via its processed file rather than its
  data source
- MAINT: List view includes the task error for proper error reporting

v1.66.2 (05Feb26)
-----------------

- BUG: A file is checked to exist, which confirms a finished upload, before it is read

v1.66.1 (12Dec25)
-----------------

- BUG: Fixed logic flaw in shared permissions

v1.66.0 (11Dec25)
-----------------

- ENH: Task state filter accepts multiple states
- BUG: Fixed API schema generation for filters that take a list

v1.65.0 (10Dec25)
-----------------

- ENH: New V2 API
- ENH: Advanced support for organizations
- ENH: Advanced permissions for organizations
- ENH: Unified permission REST endpoints
- ENH: Lazy delete (recycle bin) for faster endpoint response
- ENH: Custodian that regularly cleans up the database (lazy deletion)
- ENH: Uploading ZIP containers
- ENH: Query for multiple surfaces or tags
- ENH: Enhanced workflow routing
- ENH: User responses include the email verification status
- ENH: Serializers support dynamically selected fields
- ENH: Endpoint for the intersection of permission sets
- ENH: Endpoint that returns the tag tree with counts
- ENH: Analysis results record their creator
- ENH: Surface and topography responses include the current user's access level
- ENH: Option for models to dynamically choose their Celery routing target
- PERF: Much faster thumbnail loading
- ENH: Objects can be resolved via ID or URL
- ENH: Standardized permissions response
- API: User searches are limited to the user's organizations
- API: Permissions now return the id, URL and permissions of the current user
- API: Creator now returns the id, URL and username
- API: Surfaces and topographies are ordered alphabetically by default
- API: Permission set responses include the id and URL
- MAINT: Refactored internal analysis models into workflow models
- MAINT: Removed automatic creation of the default group "all"
- MAINT: Periodic tasks are routed to the manager queue
- MAINT: Compact user and organization representations reduce extra API calls
- MAINT: Return the task id and the launcher task id
- MAINT: User view generates usernames
- MAINT: Consistent use of filters for the V2 API
- MAINT: Updated manager filters for V2 and aligned surfaces V2 with the other V2 changes
- MAINT: Workflow endpoint supports ordering
- MAINT: Disabled logging of task progress
- MAINT: Added tests for manager V2 and fixed issues found in testing
- MAINT: Renamed the upload confirmation flag to a confirmation timestamp
- MAINT: OpenAPI annotations
- MAINT: Serializers for the shared permission sets endpoint
- BUG: ZIP container creation is routed to the manager Celery queue
- BUG: Fixed check of user permissions in serializer
- BUG: Return the permission set URL in serializer
- BUG: Fixed custodian bug referencing a non-existent field
- BUG: Deleted topographies are no longer returned when their surface is not deleted
- BUG: Filtering by presence of tags works, since Django skips filters without a value
- BUG: User lists no longer contain duplicates
- BUG: Fixed granting permissions
- BUG: Creating a file record also creates its permission set
- BUG: Tag prefix filter works on tags with spaces
- BUG: Fixed serializer changes lost in a rebase
- BUG: Topography filter takes the tags of the surface into account
- BUG: The data source of a topography is writeable
- BUG: NUL characters, which PostgreSQL cannot store, are stripped from error messages
- BUG: Related-object fields accept either an id or a URL as input
- SEC: Fixed two vulnerabilities found in the security audit
- SEC: Fixed all critical vulnerabilities found in the security audit

v1.64.3 (20Jul25)
-----------------

- BUG: Fixed conversion of a list of ids to a string

v1.64.2 (28Jul25)
-----------------

- BUG: Skip failed analyses when preparing download
- BUILD: Bumped SurfaceTopography to 1.18.2 (bug fix in JPK reader)

v1.64.1 (28Jul25)
-----------------

- MAINT: Fixed weird characters in digital surface twin names

v1.64.0 (28Jul25)
-----------------

- BUILD: Bumped Django to 5.2 LTS and switched to ASGI
- MAINT: Don't delete analyses when refreshing the cache, but mark them as invalid

v1.63.0 (25May25)
-----------------

- ENH: Return task progress messages
- MAINT: Don't delete analyses when refreshing the cache, but mark them as deprecated

v1.62.4 (21May25)
-----------------

- BUG: Disabled deletion of old analyses during cache refresh

v1.62.3 (20May25)
-----------------

- BUG: Delete analyses before refreshing the cache

v1.62.2 (18May25)
-----------------

- BUG: Proper exception when a workflow does not declare its dependencies

v1.62.1 (11May25)
-----------------

- BUG: Fixed permissions for imported containers
- MAINT: Support for JSON serialization of xarrays

v1.62.0 (08May25)
-----------------

- ENH: Endpoint for setting permissions on workflow results, to share a saved result with another
  user
- BUG: Fixed JSON encoding of masked arrays

v1.61.2 (05May25)
-----------------

- BUG: Make sure all keyword arguments are always filled

v1.61.1 (05May25)
-----------------

- API: The error of an analysis is reported as the task error
- API: Return validation errors in the body of a 400 response
- BUG: Do not fill missing keyword arguments, so that an analysis result remains findable
- BUG: Store scheduled dependencies

v1.61.0 (05May25)
-----------------

- API: Analysis start and end times are reported as task start and end times
- ENH: Workflow templates
- ENH: Import properties from ZIP containers
- MAINT: The command for importing surfaces is renamed to refer to datasets
- MAINT: The task submission time is recorded, which allows better failure detection

v1.60.1 (27Apr25)
-----------------

- BUG: More robust task state reporting

v1.60.0 (27Apr25)
-----------------

- API: Asynchronous preparation of ZIP downloads

v1.59.0 (26Apr25)
-----------------

- ENH: Download of tags

v1.58.5 (14Apr25)
-----------------

- API: Sync functions by name, not display name

v1.58.4 (08Apr25)
-----------------

- TST: Allow ignoring specific keys in tests

v1.58.3 (07Apr25)
-----------------

- BUG: Fixed a crash in surface download caused by a missing variable

v1.58.2 (04Apr25)
-----------------

- BUG: Handle lookups that unexpectedly return multiple objects

v1.58.1 (04Apr25)
-----------------

- BUG: Account handling works without sign-in and sign-out URLs

v1.58.0 (04Apr25)
-----------------

- ENH: Optional description for workflow results
- MAINT: allauth URLs are no longer added automatically

v1.57.4 (02Apr25)
-----------------

- MAINT: Default to the simple API router in production

v1.57.3 (19Mar25)
-----------------

- MAINT: Internal flag for disabling filters when reading a file

v1.57.2 (17Mar25)
-----------------

- BUG: Fix download of multiple digital surface twins

v1.57.1 (16Mar25)
-----------------

- MAINT: Order analyses by start time, newest first

v1.57.0 (15Mar25)
-----------------

- ENH: Pagination for all list requests
- ENH: Filtering for all list requests
- ENH: Advanced filtering and searching in surface list view
- ENH: Querying computed analyses
- ENH: Deleting named analyses
- API: Removed queries by function id; query workflows by name

v1.56.0 (04Mar25)
-----------------

- ENH: Delete endpoint for workflow results
- BUG: Return 400 bad request when creation of download ZIP fails
- BUG: Gracefully handle missing file records
- MAINT: Fixed a pint deprecation
- MAINT: Moved all HTML user pages to ce-ui
- BUILD: Bumped SurfaceTopography dependency to 1.18.1

v1.55.2 (16Feb25)
-----------------

- BUG: Graceful failure of squeezed file creation

v1.55.1 (16Feb25)
-----------------

- BUG: Fixed URL paths for setting tag permissions and for listing properties in a tag
- BUG: Graceful failure of thumbnail or deep zoom creation

v1.55.0 (09Feb25)
-----------------

- API: Analysis functions are looked up by name, not id
- ENH: Convenience methods for reading and writing JSON and NetCDF files
- MAINT: Renamed analysis functions to workflows
- MAINT: Removed notification on dataset changes
- MAINT: Removed request counter middleware

v1.54.0 (08Feb25)
-----------------

- API: Changed URL for getting names of properties in tags
- BUG: Login checks use the REST framework's authentication instead of Django's login decorator
- BUG: Return 404 when tag does not exist
- BUG: Permission errors are reported to the user

v1.53.3 (02Feb25)
-----------------

- BUG: Fixed getting numerical and categorical properties of tags

v1.53.2 (23Jan25)
-----------------

- BUG: Fixed names of Dropbox settings

v1.53.1 (23Jan25)
-----------------

- ENH: Return name of analysis in API responses

v1.53.0 (23Jan25)
-----------------

- ENH: Endpoint for querying pending or started analyses
- MAINT: Functions now have a fully qualified name and a display name
- BUG: Copy attachments and properties when deep-copying a digital surface twin
- BUG: Asking for named results without specifying a name no longer returns all results

v1.52.4 (16Dec24)
-----------------

- MAINT: Link to download of data in API self-reporting
- MAINT: Clear task error when resubmitting

v1.52.3 (09Dec24)
-----------------

- MAINT: Allow allauth headless mode

v1.52.2 (05Dec24)
-----------------

- BUG: Ignore type errors when constructing task progress

v1.52.1 (04Dec24)
-----------------

- BUG: Fixed a URL name lookup

v1.52.0 (11Dec24)
-----------------

- ENH: Return analysis dependencies from REST API
- ENH: Entry-point endpoint
- ENH: Full headless mode for allauth
- BUG: Propagate dependency errors

v1.51.0 (25Nov24)
-----------------

- ENH: Query topographies for multiple surfaces at once
- BUG: Report missing permission when the requested analysis implementation does not exist

v1.50.3 (13Nov24)
-----------------

- BUG: Allow logged-in users to access user data
- BUG: Exclude the anonymous user from search results

v1.50.2 (13Nov24)
-----------------

- BUG: Graceful handling of files without file names

v1.50.1 (13Nov24)
-----------------

- MAINT: Removed accidental jedi dependency

v1.50.0 (12Nov24)
-----------------

- API: Objects now include links to auxiliary API endpoints
- API: Tags are now referred to uniquely by their name instead of their id in the API
- API: Properties are returned as dictionaries (key-value pairs)
- ENH: Generic attachments for digital surface twins and measurements
- ENH: Surfaces are now returned for all tag children
- ENH: Validation of analysis parameters
- ENH: Dependencies between analyses
- ENH: New API endpoint to retrieve a single tag
- ENH: Analysis results can be saved, protecting them from deletion
- BUG: Avoid properties with identical names
- BUG: Tag analysis only runs on subjects to which the user has access
- MAINT: Replaced bare file fields with a unified file-manifest system that handles storage, upload
  and download
- MAINT: Replaced django-guardian with a simpler authorization system
- MAINT: Validation of instrument parameters using the new pydantic metadata definition in
  SurfaceTopography 1.17.0 and later
- TST: Moved all tests into a new top-level directory

v1.8.1 (13Jul24)
----------------

- BUILD: Bumped dependencies to remove muSpectre and introduce muFFT
- BUG: Return permission denied instead of an internal server error when an analysis does not exist
- BUG: Skip permission check if there are no surfaces in the subjects

v1.8.0 (12May24)
----------------

- API: The numerical and categorical flags of properties are now attributes rather than methods
- ENH: Tags can report all properties of their surfaces
- MAINT: JSON serialization of JAX arrays

v1.7.3 (22Mar24)
----------------

- BUG: Fixed version discovery

v1.7.2 (21Mar24)
----------------

- MAINT: Replaced Tagulous fields of properties with plain text fields to remove a race condition
- BUILD: Bumped SurfaceTopography to 1.13.12

v1.7.1 (14Mar24)
----------------

- ENH: Report memory usage of inspection tasks
- ENH: Report sum and maximum of data points when reporting memory usage of analysis tasks

v1.7.0 (12Mar24)
----------------

- ENH: Properties as key-value pairs with categorical and numerical values, including units
- ENH: Export properties to the metadata of ZIP containers
- ENH: Tags as analysis subjects (replacing surface collections)
- ENH: Import of ZIP containers from a URL

v1.6.1 (30Jan24)
----------------

- BUILD: Updated to django-allauth 0.56.0 or later
- MAINT: Redirect to S3 instead of serving published surface containers from Django
- MAINT: Run linting via pre-commit before commits

v1.6.0 (22Jan24)
----------------

- ENH: API returns creation and modification times
- MAINT: Creation time is now the publication date, or empty if unknown (it was set to the date of
  an earlier migration)

v1.5.0 (20Jan24)
----------------

- ENH: API endpoint to retrieve version information
- ENH: Tracing and reporting of memory usage of analysis tasks
- ENH: Manager and analysis tasks are routed to different Celery queues
- ENH: More options for filtering by sharing and publication status
- ENH: Plugins can register middlewares and context processors
- ENH: Plugin versions are now stored for each analysis
- BUILD: Updated Django to the 4.2 LTS release (the 3.2 LTS release is no longer supported after
  April 2024)
- MAINT: Split the user interface into a separate app in its own git repository
- MAINT: Split publication functionality into a separate git repository and made it an optional
  dependency
- MAINT: Changed django-guardian from generic to direct foreign keys
- MAINT: Enforce PEP-8 style

v1.4.5 (09Dec23)
----------------

- MAINT: Allow staff users to manually force cache renewals
- BUILD: Updated SurfaceTopography to 1.12.2 (fixes SPM reader)

v1.4.4 (27Nov23)
----------------

- BUG: Fixed download of TXT, CSV or XLSX if one of the analyses has an error

v1.4.3 (26Nov23)
----------------

- BUG: Fixed wrongly encoded subject when clicking analyze in the topography detail view

v1.4.2 (26Nov23)
----------------

- MAINT: Hide user interface elements rather than disabling them
- MAINT: Disallow selection for batch editing of published topographies
- MAINT: Disable edit button in permissions card when permissions cannot be edited

v1.4.1 (25Nov23)
----------------

- MAINT: Order measurements in digital surface twin
- BUG: Bokeh plot wrapper did not properly define glyphs when selection is possible
- BUG: Watch data source changes in Bokeh plot wrapper

v1.4.0 (25Nov23)
----------------

- ENH: Batch upload
- ENH: File errors are properly reported to the user
- ENH: Button to regenerate cached properties such as thumbnails and DZI
- ENH: Added select filter options "shared by you" and "published by you"
- ENH: Added creation and last modified datetime to surfaces and topographies
- ENH: Simplified sharing, now including ownership transfer
- BUG: Fixes related to uploading files
- BUG: Fixed automatic extraction of instrument parameters for some file formats
- MAINT: Removed database URL configuration from the container entrypoint
- MAINT: BokehJS is now used for plotting line scans
- MAINT: Surface view is now largely a single-page application
- MAINT: REST API for topography handling
- MAINT: Major refactor of task handling code
- MAINT: Refactored codebase to respect the hierarchy of Django apps
- MAINT: Cached topography properties (thumbnails, DZI, etc.) are now generated in a single task
- MAINT: Removed Python Bokeh dependency
- BUILD: Updated SurfaceTopography to 1.12.1

v1.3.1 (13Sep23)
----------------

- BUG: Return raw ids in addition to API URLs (fixes analysis download)
- BUG: Limit list of analysis functions based on user permissions

v1.3.0 (11Sep23)
----------------

- ENH: Updated SurfaceTopography to 1.11.0 (adds support for JPK files, fixes for DATX files)
- MAINT: Removed use of Django's content type framework and generic relations for analysis subjects
- MAINT: Moved logic for triggering tasks (cache renewal or analyses) to the data models
- PERF: Performance optimizations, e.g. prefetching of datasets

v1.2.5 (30Aug23)
----------------

- BUILD: Updated SurfaceTopography to 1.10.1

v1.2.4 (29Aug23)
----------------

- ENH: Updated SurfaceTopography to 1.10.0 (adds support for PLUX and WSXM files, fixes for GWY and
  text files)

v1.2.3 (28Aug23)
----------------

- ENH: Updated SurfaceTopography to 1.9.0 (adds support for OIR and POIR files, fixes for SUR and
  LEXT files)

v1.2.2 (21Aug23)
----------------

- MAINT: More fixes to CSRF token injection

v1.2.1 (04Aug23)
----------------

- MAINT: Unified CSRF token injection

v1.2.0 (01Aug23)
----------------

- ENH: DOI badge
- ENH: Sidebar instead of dropdown for notifications and user menu
- BUG: Plot collapses when switching back to web view
- BUILD: Updated SurfaceTopography to 1.8.0 (adds support for LEXT and DATX files, fixes for
  Mitutoyo files)
- MAINT: Only load the analysis results that the user wants to see
- MAINT: Fixed sort order of analysis downloads
- MAINT: Added django-request-profiler middleware

v1.1.3 (27Jun23)
----------------

- BUILD: Updated SurfaceTopography to 1.7.0 (adds support for PLU, FRT and HFM files)

v1.1.2 (17Jun23)
----------------

- BUG: Fixed missing imports

v1.1.1 (16Jun23)
----------------

- BUG: More robust handling of complete worker failures
- MAINT: Removed dependency on unused celery-progress package

v1.1.0 (11Jun23)
----------------

- ENH: Unified single-page application for analyses, including rewritten task status
- ENH: Webpack-based bundling for the analysis app
- ENH: CSV download for analyses
- ENH: Upgrade to Vue 3
- MAINT: Converted pickled binary dictionaries to JSON fields
- MAINT: Analysis functions now have permalinks
- MAINT: Analysis downloads now contain instrument information
- MAINT: Analysis downloads are now in SI units
- MAINT: Additional assorted fixes

v1.0.5 (17Apr23)
----------------

- BUILD: Upgrade of SurfaceTopography to 1.6.2

v1.0.4 (10Apr23)
----------------

- BUG: Duration of an analysis is no longer a computed property

v1.0.3 (06Apr23)
----------------

- BUG: Plugin version configuration could not be saved if there are changes on top of the semantic
  version

v1.0.2 (06Apr23)
----------------

- BUILD: Upgrade of SurfaceTopography to 1.6.0

v1.0.1 (02Feb23)
----------------

- BUG: Fixed comparative analysis
- BUG: Remove copy of surface when publication fails

v1.0.0 (31Jan23)
----------------

- ENH: Surface collections as analysis subjects, allowing analysis functions that process several
  surfaces together
- ENH: DOIs related to analyses are included in downloads and shown with results in the standard
  plot card view
- ENH: Creation time of analyses is saved and shown in the task dialog
- BUG: Fixed problem loading SUR files
- BUG: Fixed problem with surface collection name
- MAINT: Fine-grained enabling of navigation tabs via settings
- MAINT: Moved allauth-dependent views into a separate module
- MAINT: Added license information to version information dialog
- MAINT: Improved log messages of the image creation command
- MAINT: Fixed missing plugin list for Docker image in production
- MAINT: Removed Firefox from production Docker image
- MAINT: Renamed "Sign in via ORCID" to "Sign in"
- MAINT: AWS access information defaults to none
- MAINT: Added django-watchman health checks, including a Celery check
- BUILD: Upgrade of SurfaceTopography to 1.3.3

v0.92.0 (14Dec22)
-----------------

- ENH: Store bibliography (DOIs) when an analysis completes
- ENH: Search also matches names of users who created digital surface twins or measurements
- ENH: Also show names of creators of unpublished digital surface twins and measurements in search
  results
- ENH: When hovering on a data point, also display measurement name and series name
- ENH: Made "Tasks" information more prominent and added possibility to renew selected analyses in
  the UI
- ENH: Added command giving a user restricted admin permissions to edit organizations or check the
  state of analyses
- ENH: Image creation command can process thumbnails and DZI files separately and generate only
  missing images
- ENH: Added link to admin interface for staff users
- ENH: Added configuration options (enabled by default) to disable publications and the tab with own
  publications
- BUG: Fixed crashing of plots when an apostrophe was used in the subject's name
- BUG: Fixed problem when a surface was part of an analysis collection
- MAINT: Close figures after generating plots from 1D measurements
- MAINT: Added plugin system; statistical analysis and contact mechanics moved to separate plugins
- BUILD: Update of SurfaceTopography
- BUILD: Update of ContactMechanics
- SEC: Update of Django because of a security issue

v0.91.1 (19Sep22)
-----------------

- ENH: Added "Authors" tab in detail page for published digital twins
- ENH: Added links to contact.engineering paper
- BUG: Fixed renewed bandwidth cache not being saved
- SEC: Security update for Django and oauthlib

v0.91.0 (05Aug22)
-----------------

- ENH: Show unreliable bandwidth in a different color in bandwidth plot
- ENH: Added command to renew the bandwidth cache of all measurements, including the short
  reliability cutoff
- BUG: Fix for parallel generation of identical version numbers
- BUG: Fix for missing import when generating thumbnails
- BUG: Surface import command now saves to the database after updating the file name and before
  generating the squeezed file
- BUG: Fixed layout of measurement form
- MAINT: Image creation command counts failed images as failed by default
- MAINT: Changed Redis health beat check intervals
- MAINT: Removed some old template code

v0.90.3 (27Jul22)
-----------------

- ENH: Fixed navigation bar including basket while scrolling
- BUG: Fixed wrong contact mechanics details being shown
- BUG: Fixed missing progress bars for unready analyses
- BUG: Fixed impossible return to plot tab
- BUG: Fixed missing download link for contact mechanics
- BUILD: Bumped SurfaceTopography to 1.0

v0.90.2 (11Jul22)
-----------------

- PERF: Fewer redundant SQL queries and fewer storage requests by loading only plot metadata, not
  plot results, when preparing plots
- MAINT: Automatically create a storage bucket in MinIO S3 of the development Docker environment
- SEC: Security updates for Django and lxml

v0.90.1 (27Jun22)
-----------------

- MAINT: Presign in separate request when loading analysis data
- PERF: Some optimization of SQL requests
- SEC: Security fixes (numpy, flower)
- MAINT: No longer use compiled numpy package because of broken wheel
- MAINT: Order of analysis result cards now matches order of chosen checkboxes

v0.90.0 (30May22)
-----------------

- ENH: Moved plot creation from backend to frontend, speeding up plot creation and data loading
- ENH: Buttons to hide/show data sources now show the color of the data source next to them
- ENH: Show hierarchy of digital twins/measurements in plots
- ENH: User-switchable legend for plots
- ENH: Download plots as SVG vector graphics
- ENH: Same digital twins/measurements have the same colors across all plots
- ENH: Line style is also shown in plot legend
- ENH: Added slider for line widths to plots
- ENH: Sorted functions by name
- ENH: Increased step size for maximum number of iterations in contact mechanics
- ENH: Improved filenames of downloaded containers
- BUG: Fixed logscale labels
- BUG: Renamed y-label of curvature distribution to probability density
- BUG: Fixed step filename in the CSV plot data of contact mechanics downloads
- BUG: Plastic calculation now resets plastic displacement before each optimizer run
- BUG: Fixed automatic redirection from HTTP to HTTPS
- MAINT: Fixed typo on landing page
- SEC: Some dependency updates because of security issues
- MAINT: Added temporary redirect to challenge URL

v0.20.1 (13Apr22)
-----------------

- BUG: Added missing database migration

v0.20.0 (13Apr22)
-----------------

- BUG: Explicitly create plastic system if hardness is specified
- BUG: Fix for thumbnail creation
- BUG: Fix for redundant thumbnail files
- MAINT: Removed Selenium dependency; thumbnail generation now uses Pillow and matplotlib
- MAINT: Store topography data and derived data (squeezed files, thumbnails) under a unique prefix

v0.19.1 (23Mar22)
-----------------

- MAINT: Adjusted Docker Swarm production setup to use Redis, removed Memcached and RabbitMQ

v0.19.0 (23Mar22)
-----------------

- ENH: Added possibility to assign DOIs to published datasets
- ENH: Added command to renew containers
- ENH: Analysis trigger command can trigger analyses for all topographies of given surfaces
- MAINT: Switched cache backend and Celery broker to Redis because of problems with RabbitMQ and
  Memcached
- SEC: Updated Django and Pillow because of CVEs

v0.18.2 (26Jan22)
-----------------

- BUG: Fixed missing NetCDF files in contact mechanics download
- BUG: Fixed contact calculations always pending after triggering them manually
- BUG: Fixed unit issue in contact mechanics for measurements with missing data
- BUG: Now limiting size of measurements for contact mechanics
- BUG: Fix for Memcached error
- MAINT: Workaround for failing thumbnails in production
- MAINT: Updated Docker Swarm configuration because of connection failures in production

v0.18.1 (14Jan22)
-----------------

- MAINT: Added missing changes to run with a new certificate and a local Docker repository

v0.18.0 (14Jan22)
-----------------

- ENH: Faster visualization of image maps for 2D measurements and contact mechanics by precomputing
  detail levels with DeepZoom
- ENH: Improved layout of surface list on the Find&Select tab
- ENH: Improved layout of contact mechanics analyses
- ENH: Faster access to bandwidths of measurements due to caching in database
- ENH: Creation of images for measurements can be triggered in background via a command
- ENH: Fixed second navigation bar
- BUG: Fixed progress meter flaws for slope-dependent properties
- BUG: Fixed insufficient number of arguments for contact mechanics calculation
- BUG: Fixed scheduled PostgreSQL backups
- MAINT: Avoid loading full measurements in the Django server, allowing larger measurements
- MAINT: A "surface" is now called "digital surface twin"
- SEC: Upgrade of multiple packages because of CVEs (Django, Celery, lxml, Pillow)

v0.17.0 (03Dec21)
-----------------

- ENH: Detection and optional filling of missing data points
- MAINT: Measurement size in download metadata is now a list instead of a tuple, so a safe YAML
  loader can read it
- MAINT: Upgrade of reverse proxy Caddy in production
- MAINT: Preparations for running on Docker Swarm

v0.16.2 (15Nov21)
-----------------

- BUG: Fixed unicode conversion issue in OPDx reader
- BUG: Fixed wrong condition in the height scale fix command
- BUG: Missing permissions in Docker container to start PostgreSQL server
- BUILD: Upgrade to SurfaceTopography 0.99.1

v0.16.1 (25Oct21)
-----------------

- BUG: Fixed missing manifest entry during installation by using another package for Font Awesome 5
  icons
- BUG: Fixed error messages when surface analysis succeeds but no measurement analysis does
- BUG: Fixed wrong import which broke the user notification command
- BUG: Fixed alignment of 2D PSD data to 1D PSD data
- BUG: Fixed reliability cutoff removing entire measurement
- BUG: Improved error message in case of server error in analysis result
- BUILD: Upgrade to SurfaceTopography 0.98.2

v0.16.0 (18Oct21)
-----------------

- ENH: Search supports web-like expressions: phrases are combined with AND, and OR and - (for NOT)
  can be used
- ENH: Only measurements matching the search expression are now shown underneath surfaces
- ENH: Reliability analysis for scanning probe data
- ENH: Scale-dependent curvature
- ENH: Added links to GitHub discussions
- ENH: Show publication authors on Find&Select page
- BUG: Scale-dependent slope is now computed using the brute force approach
- BUG: Fixed downloading analysis results with stderr for y without masked values
- BUG: Missing points were not shown correctly in 2D plots
- BUG: Fixed height scale applied twice on import
- BUG: Fixed continuing average along x after data is completed
- BUG: Fixed analyses not being recalculated when instrument parameters change
- BUG: Resolution or tip radius no longer mandatory when an instrument type has been chosen
- MAINT: Computing of averages is handled by SurfaceTopography
- MAINT: All properties are averaged to a reasonable number of data points
- MAINT: Decapitalized analysis function names (e.g. "Roughness Parameters" -> "Roughness
  parameters")
- MAINT: Removed error bars on analysis results
- BUILD: Upgrade to Django 3.2
- BUILD: Upgrade to Font Awesome 5
- BUILD: Upgrade to PostgreSQL 13.4
- BUILD: Upgrade to SurfaceTopography 0.98.0
- BUILD: Upgrade to ContactMechanics 0.91.0
- BUILD: Upgrade of several other packages
- SEC: Upgrade of sqlparse because of a CVE

v0.15.1 (05Aug21)
-----------------

- BUG: Removed unneeded form fields for instrument details

v0.15.0 (05Aug21)
-----------------

- ENH: Instrument details for measurements (name, type, type-specific parameters; default type
  undefined), for later reliability analysis
- ENH: Improved layout of XLSX analysis downloads for height, slope and curvature distributions,
  power spectrum, autocorrelation, scale-dependent slope and variable bandwidth
- ENH: Added anonymous distribution of measurement uploads over users to the usage statistics Excel
  file
- ENH: Added support for SPM files as newer DI files that contain 32-bit data
- BUG: Unified order of measurements in surface details and when switching between measurements
- BUILD: Upgrade of several dependencies, e.g. SurfaceTopography to 0.95.1
- SEC: Upgrade of urllib3 because of a CVE
- TST: PostgreSQL is now also used for tests because of JSON fields

v0.14.0 (01Jul21)
-----------------

- ENH: Added upper and lower bound of bandwidth to roughness parameter table
- ENH: First column of the roughness parameter table on the "Analyze" tab is no longer
  width-restricted; horizontal scrollbar added
- ENH: Containers of published surfaces are cached on first download, and can be downloaded directly
  via the publication URL
- ENH: Added note on how to stop animation in the thumbnail gallery
- ENH: New command to align topography sizes in the database with those reported by
  SurfaceTopography
- ENH: Added summary page with monthly numbers to usage statistics; sheets now sorted with the
  latest date first
- BUG: Fixed wrong topography in plots and analysis results after changing significant fields such
  as detrend mode (since 0.13.0)
- BUG: Workaround for an exception sometimes raised when creating new topographies
- BUG: Fixed missing commas in BibTeX and BibLaTeX citations
- BUG: Fixed statistics in output when correcting height scales via command
- BUG: Fixed cryptic error messages for analyses on reentrant line scans and display of "infinity"
  in roughness parameter table
- BUG: Improved error message if interpolation for averaging fails, showing the failing measurement
- BUG: Fixes in output of the height scale fix script

v0.13.0 (16Jun21)
-----------------

- PERF: Faster upload of new measurements by running jobs in the background and reducing file loads
- PERF: Faster loading of measurements from an internal squeezed data file; added command to
  recreate these files
- ENH: Added publication date next to version number in table on select page
- ENH: Added 1D RMS curvature values for line scans and maps to table with roughness parameters
- ENH: Added command to fix height scales
- BUG: Fixed failing curvature distribution for uniform line scans
- BUG: Fixed loading of 2D XYZ files
- BUG: Fixed incorrect scaling for OPD files
- BUG: Fixed internal error in contact mechanics analysis card in certain cases
- BUG: Fixed count when deleting analysis functions
- BUG: Renamed detrend mode option "Remove curvature" to "Remove curvature and tilt"
- ENH: Made bandwidth plot more slender for surfaces with only one measurement
- BUILD: Upgraded to SurfaceTopography 0.94.0
- SEC: Several dependency updates for security reasons

v0.12.0 (20May21)
-----------------

- ENH: Use the acquisition time from the data file, if present, as initial measurement date after
  upload
- ENH: Add buttons to select and deselect all measurements and averages in analysis result plots
- PERF: Load the plot in the background when viewing a measurement, for faster page access
- BUG: Fix internal server error caused by failing thumbnail generation
- BUG: Show a friendlier server error page with a contact link and a button to go back to the site
- BUG: Fix server error when downloading PSD analysis data for surfaces with only one measurement

v0.11.1 (11May21)
-----------------

- BUG: Add missing database migrations

v0.11.0 (10May21)
-----------------

- ENH: Add "Download" button for individual surfaces to the "Select" page
- ENH: Add "Download" button for all surfaces related to the current selection
- ENH: Make two averages distinguishable in plot widgets by adding the version number to the label
  if one is published
- ENH: Rename analysis "RMS Values" to "Roughness Parameters"; add columns "from" and "symbol" and
  more values, show numbers as decimal powers
- ENH: Use scientific notation with powers of 10 instead of "e" notation on plot axes
- ENH: Move colorbar labels next to the colorbars
- ENH: Rename data series "RMS height/slope/curvature" to "Gaussian fit" in height, slope and
  curvature distribution results
- API: Change the surface container format so that measurements can hold multiple data files later
- BUILD: Upgrade to SurfaceTopography 0.93.0
- SEC: Upgrade to Django 2.2.20 because of a CVE
- SEC: Upgrade py and django-debug-toolbar because of CVEs
- BUG: Fix missing average curve when a surface was selected by tag only
- BUG: Fix administrative command that stores default analysis function arguments

v0.10.1 (31Mar21)
-----------------

- BUILD: Upgrade pip in the Docker image so that no Rust is needed to install the cryptography
  package

v0.10.0 (31Mar21)
-----------------

- ENH: Add surface analyses averaging over all topographies of a surface for "Power Spectrum",
  "Autocorrelation" and "Variable Bandwidth", based on a more generic analysis model
- ENH: Add analysis function "Scale-dependent Slope", which also calculates an average over a
  surface
- ENH: Show the surface name in plot tooltips to distinguish topographies with the same name
- ENH: Add widget for choosing the opacity of topographies to analysis plots
- MAINT: No longer create an example surface for new users, since published surfaces are accessible
  to all users
- ENH: Add missing metadata for surfaces and topographies to the surface container download; the
  format can now hold multiple surfaces and licenses
- MAINT: Add administrative command to import surface containers previously downloaded from the web
  app
- DOC: Add a short description on the surface landing page
- DOC: Add a short description for the bandwidth plot
- ENH: Remove plot titles from many plots where they are not needed
- MAINT: Change the contact mail address
- BUILD: Upgrade to SurfaceTopography 0.92.0, which returns the nonuniform PSD only up to a
  reasonable wavevector
- SEC: Upgrade Pillow, Jinja, lxml, PyYAML, Pygments and Django because of CVEs
- ENH: Show numpy and scipy versions in the version information and track them for analyses from now
  on

v0.9.6 (04Dec20)
----------------

- ENH: Show the license when viewing a published surface
- ENH: Show "Please wait" label on the contact mechanics "Recalculate" button when pressed
- BUG: Fix load error in some cases when searching
- BUG: Fix database error in logs when an analysis finished after its topography was deleted; such
  analyses are now deleted
- BUG: Fix error when too many topographies were selected

v0.9.5 (01Dec20)
----------------

- ENH: New layout with a menu bar instead of tabs, a selection bar below the menu bar and nicer
  vertical pills
- ENH: Add counter for total requests
- BUG: Fix RMS table in case of NaN values
- ENH: Show a placeholder thumbnail if a thumbnail is missing
- BUG: Fix possibly wrong versions in contact mechanics download
- BUILD: Switch back to the original django-tagulous package

v0.9.4 (23Nov20)
----------------

- ENH: Add analysis function "RMS Values"
- ENH: Autoscroll the selected row into view on the select tab
- ENH: Improve bandwidth plot: remove labels, add an info box on hover with name and thumbnail of
  the topography
- ENH: Allow custom sorting of the sharing info table
- ENH: Usage statistics can be sent by email
- BUG: Fix wrong select tab state in session
- ENH: Rename button "Properties" to "View"
- ENH: Show only the first line of descriptions on the select tab, the rest is expandable by button
- BUG: Fix ordering by surface name on the publication tab

v0.9.3 (12Nov20)
----------------

- SEC: Fix cross-site scripting (XSS) issues
- BUG: Fix issue with the administrative command for fixing permissions

v0.9.2 (02Nov20)
----------------

- SEC: Fix cross-site scripting (XSS) issue

v0.9.1 (02Nov20)
----------------

- BUG: Fix missing plotting dependencies in production

v0.9.0 (02Nov20)
----------------

- ENH: Users can publish their surfaces
- ENH: Allow anonymous sessions, so users can browse published surfaces and analyses without signing
  in
- ENH: Add thumbnail gallery for topographies in a surface
- ENH: Add tooltips to tab headers
- BUILD: Adjust dependencies to the new repositories resulting from the split of the PyCo package
- MAINT: Replace the plottable dependency by Bokeh for the bandwidth plot
- ENH: Add terms and conditions version 2.0
- ENH: Add anonymous counts of publication and surface views and downloads
- BUG: Fix display of applied boundary conditions for contact mechanics calculations; recalculation
  needed
- MAINT: Remove banner stating that this is a beta release

v0.8.3 (26Jun20)
----------------

- BUG: Add missing database migration for ordering of topographies

v0.8.2 (26Jun20)
----------------

- BUG: Add missing files for tab navigation

v0.8.1 (26Jun20)
----------------

- ENH: Add button to the basket which deselects all items
- ENH: Add widget for changing the page size of the result table on the "Select" page
- ENH: Save state of filters and paging on the "Select" tab in the session
- ENH: Remove "back" buttons no longer needed because of the tabbed interface
- BUG: Simplify tab titles, fixing strange tab behavior for long tab titles
- ENH: Add ">>" to tab titles to visualize the workflow
- ENH: Show tab "Analyze" only after an "Analyze" button was pressed; add "Analyze" button to the
  basket
- ENH: Replace the interactive legend in the contact mechanics plot by a collapsed list of
  checkboxes, enlarging the plot area
- ENH: Replace loading indicator for the tree on the "Select" page
- BUG: Fix wrong mail configuration in production
- BUG: Fix overlapping pills in detail view for surfaces and topographies
- BUG: Fix too many tags shown in the tag tree when filtering
- BUG: Fix missing tabs when displaying terms and conditions
- BUG: Fix wrong message in analyses view if no analyses are available but some items are selected
- ENH: Automatically trigger analyses that are about to be shown but have not been triggered yet
- ENH: When sharing a surface, ensure analyses with standard arguments of all automatic functions
  are available to the recipient
- BUG: Fix administrative command for triggering analyses; it now also replaces analyses with
  non-default arguments
- SEC: Update to Django 2.2.13 because of security issues
- SEC: Update markdown2 because of a security issue

v0.8.0 (19May20)
----------------

- ENH: Redesign the user interface
- ENH: Replace links in navigation bar and breadcrumbs by a tabbed interface; the search page is now
  called "Select"
- ENH: Place the search field in the navigation bar, so search can be done from everywhere
- ENH: Search is done server-side and results are shown page by page
- ENH: Tags can also be selected for analysis
- ENH: Remove card in detail view of topography and surface
- ENH: Add a simple CSV file with plot data to the ZIP archive of contact mechanics downloads
- ENH: Maximum number of iterations for contact mechanics calculations can be specified by the user
- BUG: Fix that retriggering of analyses could result in different default arguments
- MAINT: Add administrative script to unify function arguments of existing analyses
- BUG: Fix different number of allowed steps for automatic and manual step selection in contact
  mechanics

v0.7.6 (06Apr20)
----------------

- ENH: Contact mechanics: allow manual pressure selection by entering a list of numbers, in addition
  to automatic selection by number of values
- SEC: Upgrade Pillow because of security issues

v0.7.5 (27Feb20)
----------------

- DOC: Add help page with supported file formats, using reader descriptions from PyCo
- MAINT: Administrative command for triggering analyses can now target given functions or specific
  analyses
- MAINT: Add administrative command for sending a simple notification to all users
- ENH: More consistent orientation of topography images, including an upgrade to PyCo 0.56.0
- BUG: More robust handling of data files without channel name, which caused many exceptions and
  possibly too many database clients
- BUG: Fix wrong units of special values (mean, RMS) of slope and curvature distributions
- BUG: Fix loading of line scans without position
- BUILD: Upgrade to Django 2.2.10

v0.7.4 (14Feb20)
----------------

- ENH: Loading problems for topographies that could be loaded earlier now show an error message and
  a mailto link to report the issue
- ENH: Format detection is only done once the file has been uploaded
- ENH: Collect anonymous usage statistics in the local database; non-personal daily aggregates can
  be exported by administrators
- BUG: Avoid intermediate login page when clicking the colored boxes on the welcome page
- BUILD: Upgrade to Django 2.2.9
- BUILD: Upgrade to PyCo 0.55.0, which fixes problems with various file formats
- BUG: Fix endless recursion on 404 responses, which should also fix problems with too many database
  connections

v0.7.3 (20Dec19)
----------------

- BUG: Fix wrong orientation in topography image plots
- BUG: Fix internal server error with existing IBW files
- BUG: Fix white description in the active row of the search list

v0.7.2 (13Dec19)
----------------

- ENH: Further improve usability of the surface list
- ENH: Add menu option to mark all notifications as read
- ENH: Move tabs from card headers to the relevant places to make clear which part changes when
  switching tabs
- BUG: Replace slashes in sheet names before saving XLSX from analyses, since topography names may
  contain them
- ENH: Hide selection of topographies and series in analysis view by default and clip too long
  topography names
- ENH: In the contact plot, show on hover whether each point converged properly, together with the
  axis values
- ENH: Jump to surfaces, topographies or sharing page when clicking the statistics panel
- SEC: Upgrade Pillow because of security issues
- BUILD: Upgrade PyCo to 0.54.2
- BUG: Fix calculation of the curvature distribution for periodic surfaces
- BUG: Fix missing periodicity information that prevented PSD calculation for nonuniform
  topographies
- ENH: OPDx files can now be loaded
- BUG: Fix that topographies from HDF5 files could not be flagged as periodic
- ENH: Match aspect ratio in displacement plots
- ENH: Make task information larger and shorten unbreakable topography names with an ellipsis
- BUG: Fix color of "Recalculate" button
- MAINT: Remove unneeded whitespace in the contact mechanics README file
- ENH: If nothing is selected, show an info box that no surfaces or topographies are chosen instead
  of "Arguments for this analysis differ"

v0.7.1 (22Nov19)
----------------

- ENH: Add periodicity flag for topographies
- DOC: Add help texts explaining the asterisk in forms
- ENH: Add reference to the uploading user to the download files of analyses
- ENH: Unify "please wait" indicators when loading analysis results
- ENH: Show notification time stamps in the local time zone
- BUG: Show 403 page when accessing a surface that is no longer accessible
- BUG: Show 404 page instead of a server error for topographies that do not exist
- BUG: Fix invalid links in notifications when an object is deleted
- BUG: Fix invisible topographies in surface list when filtering by category or sharing status
- ENH: Improve some visual aspects of the surface list (not finished yet)

v0.7.0 (23Oct19)
----------------

- ENH: Surfaces and topographies can now be tagged
- ENH: Hierarchical tags can be created by inserting slashes in the tag name, e.g.
  "projects/big/part_one"
- ENH: Replace surface cards by a searchable tree listing surfaces with topographies or top-level
  tags; search by name, description and tags
- ENH: Search tree can be filtered by sharing state and category
- ENH: Use checkboxes for selecting analysis functions
- BUG: Retrigger failed analyses when they are requested again

v0.6.3 (07Oct19)
----------------

- BUG: Add database migrations needed for the bug fix in 0.6.2
- BUG: Fix setting the topography creator to empty if the uploading user is removed

v0.6.2 (07Oct19)
----------------

- BUG: Fix race conditions while managing dependency versions, which stopped new analyses

v0.6.1 (24Sep19)
----------------

- ENH: Add notifications via a bell symbol in the navigation bar for sharing changes, granted change
  access, edits of shared items, finished analyses and new example surfaces
- ENH: Plot line scans with lines; symbols are also used if there are no more than 100 points
- PERF: Save analyses for every combination of topography, function and arguments, so results for
  known parameters appear immediately
- BUG: Work around missing points in PSD plots

v0.6.0 (09Aug19)
----------------

- BUG: Fix sheet names for XLSX download of analysis data
- BUG: Fix version numbers of used dependencies, which are now tracked
- ENH: Rename tab "Failures" to "Warnings"; show incompatibilities as info, translucent points as
  warning, exceptions as error with a bug report link
- MAINT: Administrative command for triggering analyses can now retrigger failed analyses
- ENH: Port backend to PyCo 0.51.1, which can load HDF5 and OPDx files and caches file contents more
  memory-efficiently
- ENH: Show an error message when file contents are corrupt
- BUILD: Update dependencies

v0.5.7 (24Jul19)
----------------

- BUG: Work around request failures by increasing the limit for the maximum request line
- BUG: Fix server error when uploading files with a space in the filename

v0.5.6 (23Jul19)
----------------

- MAINT: Change site address for the Caddy server to just the domain name

v0.5.5 (23Jul19)
----------------

- BUG: Fix wrong heights in topography data by using PyCo 0.32.1
- ENH: Change buttons when editing topographies and add tooltips to chevron buttons to clarify batch
  editing
- ENH: Show a spinner every time a point is chosen in contact mechanics
- BUG: Work around tooltips on multiple data points in 1D plots

v0.5.4 (16Jul19)
----------------

- BUG: Fix wrong height scale if unit conversion was applied on upload; size and unit of already
  uploaded topographies may be wrong
- ENH: Add buttons and a menu entry to directly show analyses for the surface or topography being
  viewed

v0.5.3 (15Jul19)
----------------

- PERF: Fix slow PSD calculation for line scans with many data points by using PyCo 0.32.0
- ENH: Replace crosshair with inspect tool in analysis plots
- BUG: Fix wrong messages about differing function arguments
- SEC: Check permissions when downloading data

v0.5.2 (12Jul19)
----------------

- PERF: Work around slow autocorrelation computation for nonuniform topographies with many data
  points
- ENH: Add navigation chevron buttons also to the topography update form

v0.5.1 (11Jul19)
----------------

- ENH: Cosmetic changes, e.g. harmonized sizes and loading behavior of opened surface and analysis
  cards

v0.5.0 (11Jul19)
----------------

- ENH: Add contact mechanics analysis and visualization
- ENH: Add progress bars for analysis tasks
- ENH: Delete old analyses for the same topography and function
- ENH: Add download of contact mechanics data
- ENH: Add download of surface container archive
- BUG: Fix wrong unit conversion in analysis plots
- BUG: Fix sometimes wrong target of the cancel button in the upload wizard

v0.4.2 (13Jun19)
----------------

- BUG: Add missing template fragment which caused crashes in the analyses view

v0.4.1 (12Jun19)
----------------

- ENH: Allow case-insensitive search for user names
- BUG: Fix wrong task information for cards in the analyses view
- BUG: Empty surfaces can now be selected and edited
- BUG: Fix image plots of topographies
- BUG: Work around crash when uploading large files
- BUILD: Upgrade Celery, Bokeh, Caddy and Gunicorn

v0.4.0 (28May19)
----------------

- PERF: More responsive surface list through asynchronous loading
- ENH: Add progress bar when uploading a topography file
- ENH: Add statistics about shared surfaces
- ENH: Improve layout of surface search results and surface detail view; add analysis detail view
  with similar layout
- ENH: Record the user who uploaded a topography
- BUG: Fix that users could not upload topographies for shared surfaces
- BUG: Fix target of the cancel button when editing surface details

v0.3.1 (10May19)
----------------

- BUG: Fix analysis results not being shown for shared surfaces
- BUG: Fix that single topographies could not be selected in the surface list
- ENH: Require at least 3 characters when searching for user names
- BUG: Fix highlighting and breadcrumb for the "Sharing" page in the navigation bar
- ENH: Improve display of help texts in topography forms
- ENH: Truncate too long breadcrumb items in the navigation bar

v0.3.0 (08May19)
----------------

- ENH: Surfaces can be shared for viewing and optionally also for changing
- ENH: Users who collaborate, i.e. share something, can view and select each other's profiles
- ENH: List shares of a surface in an extra tab
- ENH: List all shares between users on a "Sharing" page reachable from the top menu bar
- ENH: Existing shares can be deleted or extended to allow changing a surface
- BUG: Prevent duplicate topography names within the same surface
- BUG: Topographies with angstrom units can now be displayed in the summary plot

v0.2.0 (24Apr19)
----------------

- ENH: Add category to surfaces (experimental, simulated or dummy data)
- ENH: Show units to users even if they cannot be changed
- ENH: Add widgets for picking measurement dates
- ENH: Sort bandwidth bars by lower bound in the surface summary
- ENH: Add statistics on the welcome page

v0.1 (17Apr19)
--------------

- ENH: Login via ORCID
- ENH: Creation of surfaces with metadata
- ENH: Upload of topography measurements for a surface together with metadata
- ENH: Example surface with test data for new users
- ENH: Zoom into topography or line scan plots
- ENH: Automated analyses for topographies and line scans: height/slope/curvature distribution,
  power spectrum, autocorrelation
- ENH: Compare analysis results by stitching plots
- ENH: Download of analysis results as PNG, XLSX or text file
- ENH: Ask users to accept terms and conditions, optionally also additional terms
- ENH: Storage of topography files on S3

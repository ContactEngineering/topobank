# Changelog for *TopoBank*

<!--
Style for this changelog (keep to it so entries stay uniform):

- Newest version first. Heading `vX.Y.Z (DDMonYY)`, underlined with dashes.
  A version not yet released is headed `vX.Y.Z (not yet released)`.
- One bullet per user-visible change, at most two lines (about 200
  characters). Say what changed for the user and, if useful, why or by how
  much. Omit internals: no function, class, file or variable names, no
  environment variables, no commit or PR references.
- Start every bullet with one of: `ENH:` (new feature), `BUG:` (fix),
  `API:` (interface change), `PERF:` (speed or memory), `MAINT:`, `TST:`,
  `DOC:`, `BUILD:`, `CI:`.
- Small related fixes may share one bullet. No trailing period on bullets.
-->

v1.73.1 (not yet released)
--------------------------

- BUG: Cleanup of deleted datasets no longer stops at the first dataset or
  measurement that is still referenced elsewhere; such objects are skipped

v1.73.0 (14Oct26)
-----------------

- ENH: Thumbnails and zoomable images can optionally be detrended beyond the
  measurement's own setting, so a tilted scan no longer renders as a gradient
- BUILD: Django 5.2.18
- CI: Tests run on Ubuntu 26

v1.72.0 (10Sep26)
-----------------

- ENH: Measurements and attachments upload directly to the object store, which
  enforces the size limit: 5 GiB for measurements, 100 MiB for attachments
- ENH: Attachments are served with the content type of their extension, so
  previews open in the browser; upload limits and expiry are configurable
- ENH: Every setting has a documented default, so a deployment only sets the
  values it wants to change
- ENH: Attachments carry a user note, their size and their content type, and
  keep them when a dataset is copied
- ENH: Attachment uploads are confirmed by the object store itself, so a client
  that dies after uploading no longer leaves an orphaned file behind
- API: Uploads through presigned PUT requests are no longer supported, and the
  setting that chose the upload method is gone
- API: The separate switch for S3 storage is gone; whether uploads go directly
  to the object store follows from the configured storage backend alone
- BUG: The memory guard discounts the memory a worker uses at rest, so runs on
  tiny datasets no longer make it refuse every later analysis of that workflow
- BUG: Deleting an analysis result, or a measurement with such results, no
  longer fails when the result has no permissions attached
- ENH: Analyses still pending after 7 days (configurable) because their task was
  lost, for example in a broker restart, are marked as failed
- ENH: Analysis results can be soft-deleted like datasets and measurements and
  are removed for good once the retention period has passed
- ENH: Datasets and measurements record who deleted them, so a recycle bin can
  show who deleted what while it can still be restored
- TST: The full-text search index is covered by tests
- TST: The user test factory can create users without an ORCID iD
- CI: S3 tests run against SeaweedFS instead of Minio, matching the development
  stack
- TST: The test settings exist only once and honor the configured storage, so
  the S3 tests in CI actually use S3; they had silently used the file system
- TST: A test of the temporary files of analysis containers no longer breaks
  because the S3 backend uses such files too
- BUILD: Dropped four unmaintained dependencies that were either unused or are
  covered by the standard library
- BUILD: The notifications dependency is pinned to a fixed revision instead of
  its default branch, so builds are reproducible; automated updates track it
- BUILD: Removed outdated lower bounds on seven indirect dependencies, raised
  the minimum django-allauth version and dropped the upper bound on Sphinx
- DOC: Authentication, including ORCID sign-in, is documented in ce-ui; these
  docs only describe what TopoBank requires, without naming a provider

v1.71.0 (03Aug26)
-----------------

- ENH: A data series records the range of its data, so plots can pick a fitting
  display unit without loading the data
- ENH: Measurements record the slope of the tilt and the radius of the curvature
  that detrending removed, in physical units
- ENH: Measurements record which fraction of the measured data is undefined
- ENH: Tasks whose worker disappeared are marked as failed, by the regular
  cleanup or a management command, instead of showing as running forever
- ENH: Analyses predicted to exceed the memory budget fail with an explanation
  instead of being killed by the operating system
- BUILD: The test fixtures are packaged again without a workaround that now
  made the build fail
- BUG: Whether a measurement has undefined data describes the measured data
  again; enabling filling of missing points had erased this information
- TST: The measurement test factories consistently create measurements in the
  successful state; another state can be requested

v1.70.1 (02Aug26)
-----------------

- BUG: Analyses no longer all fail once two workers registered the same
  dependency version at the same time; existing duplicates are merged
- MAINT: Requires PostgreSQL 15 or newer

v1.70.0 (02Aug26)
-----------------

- ENH: Full-text search index
- ENH: ZIP archives for downloads are created in the background
- ENH: ZIP exports accept an archive name and additional metadata
- ENH: ZIP containers are built in a temporary file that stays in memory up to a
  configurable size
- BUG: Deleting a ZIP container without a permission set no longer fails
- MAINT: Reworked rendering of line scan thumbnails
- MAINT: Physical sizes are displayed in a natural length unit
- MAINT: Removed an option of the user notification command that did nothing

v1.69.4 (25Jul26)
-----------------

- PERF: Fixed a performance issue in database migrations

v1.69.3 (24Jul26)
-----------------

- ENH: Time limits of workflow tasks are configurable, with a default hard
  limit of 6 hours
- ENH: Failed workflows also record how long each stage took, so a timeout shows
  which stage used up the time

v1.69.2 (22Jul26)
-----------------

- PERF: Tasks record their peak memory instead of tracing every allocation,
  which slowed numerical tasks about 35x; allocation tracing is opt-in
- BUG: Memory tracing is stopped when a task fails instead of slowing down all
  later tasks in the same worker

v1.69.1 (21Jul26)
-----------------

- BUG: Analysis workers no longer build links to the analyzed data, and alerts
  no longer need one

v1.69.0 (20Jul26)
-----------------

- ENH: Option to reject files with incomplete metadata
- ENH: Dataset containers keep their metadata in one validated file; the old
  metadata file is no longer written but still read on import
- ENH: Container exports accept additional metadata
- ENH: Workflows can be submitted for datasets while ignoring existing results
- ENH: Celery queue names can optionally be remapped when tasks are dispatched
- MAINT: New settings for the delay before deleted objects are removed
- MAINT: Dataset names can be up to 255 characters long
- MAINT: Tasks record which workflow requested them as a dependency
- MAINT: Admin pages for datasets and measurements pick related objects by id
  instead of from a list
- BUILD: Django 5.2.16
- BUG: A workflow fails when one of its dependencies fails, and keeps the
  dependency's traceback
- BUG: Concurrent submissions no longer create duplicate results or
  configurations
- BUG: Measurements saved with partial updates keep their pending task state
- BUG: Submitting an analysis returns the usable result, not simply the latest
- BUG: Analyses over several datasets are invalidated and cleaned up correctly
- BUG: Fixed a workflow crash related to timing; timing is recorded per workflow
- BUG: Fixed matching of existing analyses by their parameters

v1.68.0 (15Jun26)
-----------------

- ENH: Metadata can be passed when submitting an analysis
- ENH: Workflows describe their outputs with a schema
- ENH: Results can contain validated data models, which are saved as JSON
- ENH: Tasks are timed
- MAINT: The analysis list reports more information on task state
- PERF: Faster resolution of task states
- MAINT: Organizations choose their available plugins from a list instead of
  entering text
- MAINT: Plugins are handled dynamically
- BUG: Fixed permissions of the workflow view
- MAINT: Removed the usage statistics app
- MAINT: The results dictionary is deprecated
- MAINT: Resolution of dependencies is separated from task execution
- MAINT: Simplified the workflow representation in the API
- MAINT: More reliable detection of whether code runs inside a Celery task
- PERF: Performance and database index optimizations
- MAINT: Improved transaction handling
- MAINT: New setting for running behind PgBouncer
- BUILD: muFFT no longer exists and has been folded into muGrid
- BUILD: Django 5.2.10 and a newer Sphinx
- MAINT: Workflows are identified by name instead of database records, and
  analysis results refer to their subject directly
- MAINT: Removed workflow templates
- API: There is no anonymous user unless one is configured; views fall back to
  it only when it is
- BUG: Filtering workflows by plugin works for every known plugin, regardless
  of the user's organization
- BUG: Fixed the output schema; a missing workflow implementation returns
  nothing instead of failing
- BUG: Users can access the statistics backend, and the landing page works
- TST: Tests use built-in mock authentication apps instead of the ORCID plugin
- TST: Tests use Python's built-in time zones instead of pytz, and expect
  tracebacks to be passed up from dependencies

v1.67.0 (16Dec25)
-----------------

- ENH: Measurements get a NetCDF tile pyramid

v1.66.3 (07Feb26)
-----------------

- BUG: Workflows run directly after upload instead of waiting for a readiness
  check
- BUG: Fixed the check whether the data file of a measurement exists
- MAINT: The list view reports task errors

v1.66.2 (05Feb26)
-----------------

- BUG: A file is checked to exist, which confirms a finished upload, before it
  is read

v1.66.1 (12Dec25)
-----------------

- BUG: Fixed a logic flaw in shared permissions

v1.66.0 (11Dec25)
-----------------

- ENH: Tasks can be filtered by several states at once
- BUG: Fixed the API schema of filters that take a list

v1.65.0 (10Dec25)
-----------------

- ENH: New version 2 of the API
- ENH: Extended support for organizations, including their own permissions
- ENH: Unified API endpoints for permissions, with a standardized response
- ENH: Deleted objects go to a recycle bin that a regular cleanup empties, so
  delete requests return quickly
- ENH: Uploading ZIP containers
- ENH: Querying several datasets or tags at once
- ENH: Enhanced routing of workflows; objects can choose their Celery queue
- ENH: User data includes whether the email address is verified
- ENH: API responses can be limited to selected fields
- ENH: Endpoints for the intersection of permission sets and for shared
  permission sets
- ENH: Endpoint for the tag tree with the number of datasets per tag
- ENH: Analysis results record their creator
- ENH: Datasets and measurements report the current user's access level
- PERF: Much faster loading of thumbnails
- ENH: Objects can be referenced by id or by URL
- API: User searches are limited to the user's organizations
- API: Permissions report id, URL and the current user's permissions; creators
  report id, URL and username
- API: Datasets and measurements are sorted alphabetically by default
- API: Upload confirmation is reported as a timestamp
- MAINT: Analyses are stored as workflow results
- MAINT: The default group "all" is no longer created
- MAINT: Scheduled tasks run on the manager queue
- PERF: Compact user and organization data in responses saves extra API calls
- MAINT: Responses include the id of a task and of the task that launched it
- MAINT: Usernames are generated by the user view
- MAINT: Consistent filters across version 2 of the API
- MAINT: Workflow listings can be ordered
- MAINT: Task progress is no longer logged
- TST: Tests for version 2 of the dataset API, and fixes for what they found
- DOC: OpenAPI annotations for the API
- BUG: ZIP containers are created on the manager queue
- BUG: Fixed permission checks and the returned permission set link in API
  responses
- BUG: Fixed the cleanup referencing a field that does not exist
- BUG: Deleted measurements are no longer returned while their dataset exists
- BUG: Filtering on whether a dataset has tags works
- BUG: User lists no longer contain duplicates
- BUG: Fixed granting permissions, and creating permission sets for files
- BUG: Tag prefix search works for tags containing spaces
- BUG: Measurement filters take the tags of their dataset into account
- BUG: The data source of a measurement is writable
- BUG: Errors containing NUL characters, which Postgres cannot store, are saved
- BUG: Related objects in requests accept an id or a URL
- BUG: Fixed all critical vulnerabilities found in a security audit

v1.64.3 (20Jul25)
-----------------

- BUG: Lists of ids are converted to a string correctly

v1.64.2 (28Jul25)
-----------------

- BUG: Failed analyses are skipped when preparing a download
- BUILD: SurfaceTopography 1.18.2, fixing the JPK reader

v1.64.1 (28Jul25)
-----------------

- BUG: Fixed odd characters in names of digital surface twins

v1.64.0 (28Jul25)
-----------------

- BUILD: Django 5.2 LTS, served via ASGI
- MAINT: Refreshing the cache marks analyses as invalid instead of deleting them

v1.63.0 (25May25)
-----------------

- ENH: Task progress messages are reported
- MAINT: Refreshing the cache marks analyses as deprecated instead of deleting
  them

v1.62.4 (21May25)
-----------------

- BUG: Refreshing the cache no longer deletes old analyses

v1.62.3 (20May25)
-----------------

- BUG: Analyses are deleted before the cache is refreshed

v1.62.2 (18May25)
-----------------

- BUG: A clear error is raised when a workflow declares no dependencies

v1.62.1 (11May25)
-----------------

- BUG: Fixed permissions of imported containers
- MAINT: xarray data can be serialized to JSON

v1.62.0 (08May25)
-----------------

- ENH: Endpoint for setting permissions on analysis results, to share a saved
  result with another user
- BUG: Fixed JSON encoding of masked arrays

v1.61.2 (05May25)
-----------------

- BUG: All keyword arguments of an analysis are always filled

v1.61.1 (05May25)
-----------------

- API: The error field is renamed to task error
- API: Validation errors are returned in the body of the 400 response
- BUG: Missing keyword arguments are not filled, so an analysis result stays
  findable
- BUG: Scheduled dependencies are stored

v1.61.0 (05May25)
-----------------

- API: The start and end time fields are renamed to task start and end time
- ENH: Workflow templates
- ENH: Properties are imported from ZIP containers
- MAINT: The import command refers to datasets instead of surfaces
- MAINT: The time a task was submitted is recorded, for better failure detection

v1.60.1 (27Apr25)
-----------------

- BUG: More robust reporting of task states

v1.60.0 (27Apr25)
-----------------

- API: ZIP downloads are prepared asynchronously

v1.59.0 (26Apr25)
-----------------

- ENH: Download of tags

v1.58.5 (14Apr25)
-----------------

- API: Workflows are synchronized by name instead of display name

v1.58.4 (08Apr25)
-----------------

- TST: Tests can ignore specific keys

v1.58.3 (07Apr25)
-----------------

- BUG: Fixed a crash when downloading a dataset

v1.58.2 (04Apr25)
-----------------

- BUG: Lookups that match more than one object no longer crash

v1.58.1 (04Apr25)
-----------------

- BUG: Account handling works without sign-in and sign-out URLs

v1.58.0 (04Apr25)
-----------------

- ENH: Optional description for analysis results
- MAINT: The sign-in URLs are no longer added automatically

v1.57.4 (02Apr25)
-----------------

- MAINT: Production uses the simple task router by default

v1.57.3 (19Mar25)
-----------------

- MAINT: Files can be read without applying filters

v1.57.2 (17Mar25)
-----------------

- BUG: Fixed download of several digital surface twins

v1.57.1 (16Mar25)
-----------------

- MAINT: Analyses are ordered newest first

v1.57.0 (15Mar25)
-----------------

- ENH: Pagination and filtering for all lists
- ENH: Advanced filtering and searching in the dataset list
- ENH: Querying computed analyses
- ENH: Deleting named analyses
- API: Workflows are queried by name; queries by function id are gone

v1.56.0 (04Mar25)
-----------------

- ENH: Endpoint for deleting analysis results
- BUG: A failure to create the download ZIP returns 400 Bad Request
- BUG: Missing files are handled gracefully
- MAINT: Fixed a pint deprecation
- MAINT: All HTML pages for users moved to ce-ui
- BUILD: SurfaceTopography 1.18.1

v1.55.2 (16Feb25)
-----------------

- BUG: A failure to create the compact data file is handled gracefully

v1.55.1 (16Feb25)
-----------------

- BUG: Fixed the paths for setting tag permissions and for properties in a tag
- BUG: A failure to create thumbnails or zoomable images is handled gracefully

v1.55.0 (09Feb25)
-----------------

- API: Analysis functions are looked up by name instead of id
- ENH: Convenience methods for reading and writing JSON and NetCDF files
- MAINT: Analysis functions are now called workflows
- MAINT: Removed notifications on dataset changes
- MAINT: Removed the request counter

v1.54.0 (08Feb25)
-----------------

- API: Changed the URL for getting the names of properties in tags
- BUG: The API checks authentication itself instead of redirecting to sign-in
- BUG: Requests for tags that do not exist return 404
- BUG: Permission errors are reported to the user

v1.53.3 (02Feb25)
-----------------

- BUG: Fixed getting numerical and categorical properties of a tag

v1.53.2 (23Jan25)
-----------------

- BUG: Fixed the names of the Dropbox settings

v1.53.1 (23Jan25)
-----------------

- ENH: The API returns the name of an analysis

v1.53.0 (23Jan25)
-----------------

- ENH: Route for querying pending or started analyses
- MAINT: Functions have a fully qualified name and a display name
- BUG: Copying a digital surface twin also copies attachments and properties
- BUG: Querying named results without a name no longer returns all results

v1.52.4 (16Dec24)
-----------------

- MAINT: The API's self-description links to the data download
- MAINT: The task error is cleared on resubmission

v1.52.3 (09Dec24)
-----------------

- MAINT: Sign-in can run headless, without pages rendered by the server

v1.52.2 (05Dec24)
-----------------

- BUG: Type errors while building task progress are ignored

v1.52.1 (04Dec24)
-----------------

- BUG: Fixed a broken URL lookup

v1.52.0 (11Dec24)
-----------------

- ENH: The API returns the dependencies of an analysis
- ENH: Entry-point route for the API
- ENH: Fully headless sign-in
- BUG: Errors of dependencies are propagated

v1.51.0 (25Nov24)
-----------------

- ENH: Querying measurements of several datasets
- BUG: No permission is reported when a workflow implementation does not exist

v1.50.3 (13Nov24)
-----------------

- BUG: Logged-in users can access user data
- BUG: The anonymous user is excluded from search

v1.50.2 (13Nov24)
-----------------

- BUG: Files without file names are handled gracefully

v1.50.1 (13Nov24)
-----------------

- BUILD: Removed an accidental dependency on jedi

v1.50.0 (12Nov24)
-----------------

- API: Objects return links to their auxiliary API endpoints
- API: Tags are referred to by name instead of id
- API: Properties are returned as key-value pairs
- ENH: Generic attachments for digital surface twins and measurements
- ENH: Datasets are returned for all children of a tag
- ENH: Validation of analysis parameters
- ENH: Dependencies between analyses
- ENH: New route for retrieving a tag
- ENH: Analysis results can be saved, which protects them from deletion
- BUG: Properties of identical name are avoided
- BUG: Tag analyses only run on data the user has access to
- MAINT: All stored files are handled by one file model that manages upload and
  download
- MAINT: Replaced django-guardian with a simpler authorization system
- MAINT: Instrument parameters are validated against the metadata definition of
  SurfaceTopography 1.17.0 or newer
- TST: All tests moved to a new top-level directory

v1.8.1 (13Jul24)
----------------

- BUILD: Updated dependencies to drop muSpectre and introduce muFFT
- BUG: A request for an analysis that does not exist returns permission denied
  instead of an internal server error
- BUG: The permission check is skipped if the subjects contain no surfaces

v1.8.0 (12May24)
----------------

- API: Whether a property is numerical or categorical is an attribute instead
  of a method
- ENH: Tags can report all properties of their surfaces
- MAINT: JAX arrays can be serialized to JSON

v1.7.3 (22Mar24)
----------------

- BUG: Fixed version discovery

v1.7.2 (21Mar24)
----------------

- MAINT: Properties are stored as plain text to remove a race condition
- BUILD: SurfaceTopography 1.13.12

v1.7.1 (14Mar24)
----------------

- ENH: Memory usage of inspection tasks is reported
- ENH: Memory reports of analysis tasks include the sum and maximum of data
  points

v1.7.0 (12Mar24)
----------------

- ENH: Properties as key-value pairs with categorical or numerical values,
  including units
- ENH: Properties are exported to the metadata of ZIP containers
- ENH: Tags as analysis subjects, replacing surface collections
- ENH: Import of ZIP containers from a URL

v1.6.1 (30Jan24)
----------------

- BUILD: django-allauth 0.56.0 or newer
- MAINT: Containers of published surfaces are served from S3 by redirect instead
  of by Django
- MAINT: Linting runs automatically before changes are checked in

v1.6.0 (22Jan24)
----------------

- ENH: API routes return creation and modification time
- BUG: The creation time is the publication date, or empty if unknown, instead
  of the date of the migration that introduced it

v1.5.0 (20Jan24)
----------------

- ENH: API route for retrieving version information
- ENH: Memory usage of analysis tasks is traced and reported
- ENH: Manager and analysis tasks are routed to separate Celery queues
- ENH: More options for filtering by sharing and publication status
- ENH: Plugins can register middlewares and context processors
- ENH: Plugin versions are stored with each analysis
- BUILD: Django 4.2 LTS, since support for the 3.2 LTS ends in April 2024
- MAINT: The user interface moved to the separate ce-ui repository
- MAINT: Publication moved to a separate repository and is now optional
- MAINT: Object permissions use direct instead of generic foreign keys
- MAINT: The code follows PEP 8

v1.4.5 (09Dec23)
----------------

- MAINT: Staff users can force cache renewals manually
- BUILD: SurfaceTopography 1.12.2, fixing the SPM reader

v1.4.4 (27Nov23)
----------------

- BUG: Fixed TXT, CSV or XLSX download if one of the analyses has an error

v1.4.3 (26Nov23)
----------------

- BUG: The analyze button in the measurement view no longer passes a wrong
  subject

v1.4.2 (26Nov23)
----------------

- MAINT: Unavailable elements are hidden rather than disabled
- MAINT: Published measurements cannot be selected for batch editing
- MAINT: The edit button of the permissions card is disabled when permissions
  cannot be edited

v1.4.1 (25Nov23)
----------------

- MAINT: Measurements in a digital surface twin are ordered
- BUG: Line scan plots define their glyphs properly when selection is possible
  and follow changes of their data source

v1.4.0 (25Nov23)
----------------

- ENH: Batch upload
- ENH: File errors are reported to the user
- ENH: Button to regenerate cached properties such as thumbnails and zoomable
  images
- ENH: Filter options for items shared or published by you
- ENH: Surfaces and measurements show creation and last modification time
- ENH: Simplified sharing, now including transfer of ownership
- BUG: Fixes related to uploading files
- BUG: Fixed automatic extraction of instrument parameters for some file formats
- MAINT: The container entry point no longer requires a database URL
- MAINT: Line scans are plotted with BokehJS, dropping the Python Bokeh
  dependency
- MAINT: The surface view is largely a single-page application
- MAINT: REST API for handling measurements
- MAINT: Major refactoring of task handling and of the app structure
- MAINT: Cached measurement properties such as thumbnails are generated in a
  single task
- BUILD: SurfaceTopography 1.12.1

v1.3.1 (13Sep23)
----------------

- BUG: Raw ids are returned in addition to API URLs, fixing analysis download
- BUG: The list of analysis functions respects user permissions

v1.3.0 (11Sep23)
----------------

- ENH: SurfaceTopography 1.11.0, adding support for JPK files and fixing DATX
  files
- MAINT: Analysis subjects no longer use generic relations
- MAINT: Triggering of cache renewal and analyses moved into the data model
- PERF: Optimizations such as prefetching of datasets

v1.2.5 (30Aug23)
----------------

- BUILD: SurfaceTopography 1.10.1

v1.2.4 (29Aug23)
----------------

- ENH: SurfaceTopography 1.10.0, adding support for PLUX and WSXM files and
  fixing GWY and text files

v1.2.3 (28Aug23)
----------------

- ENH: SurfaceTopography 1.9.0, adding support for OIR and POIR files and
  fixing SUR and LEXT files

v1.2.2 (21Aug23)
----------------

- MAINT: More fixes to the injection of CSRF tokens

v1.2.1 (04Aug23)
----------------

- MAINT: Unified injection of CSRF tokens

v1.2.0 (01Aug23)
----------------

- ENH: DOI badge
- ENH: Sidebar instead of dropdown for notifications and the user menu
- BUG: The plot no longer collapses when switching back to the web view
- MAINT: SurfaceTopography 1.8.0, adding support for LEXT and DATX files and
  fixing Mitutoyo files
- MAINT: Only the analysis results the user wants to see are loaded
- MAINT: Fixed the sort order of analysis downloads
- MAINT: Added a request profiler

v1.1.3 (27Jun23)
----------------

- MAINT: SurfaceTopography 1.7.0, adding support for PLU, FRT and HFM files

v1.1.2 (17Jun23)
----------------

- BUG: Fixed missing imports

v1.1.1 (16Jun23)
----------------

- BUG: More robust handling of complete worker failures
- MAINT: Removed the unused celery-progress dependency

v1.1.0 (11Jun23)
----------------

- ENH: Single-page application for analyses, including a rewritten task status
- ENH: Webpack bundling for the analysis app
- ENH: CSV download for analyses
- ENH: Upgrade to Vue 3
- MAINT: Stored dictionaries are JSON instead of pickled binary data
- MAINT: Analysis functions have a permalink
- MAINT: Analysis downloads contain instrument information
- MAINT: Analysis downloads are in SI units

v1.0.5 (17Apr23)
----------------

- BUILD: SurfaceTopography 1.6.2

v1.0.4 (10Apr23)
----------------

- BUG: Fixed access to the duration of an analysis

v1.0.3 (06Apr23)
----------------

- BUG: The plugin version configuration can be saved when a version has changes
  on top of its semantic version

v1.0.2 (06Apr23)
----------------

- BUILD: SurfaceTopography 1.6.0

v1.0.1 (02Feb23)
----------------

- BUG: Fixed comparative analysis
- BUG: The copy of a surface is removed when publication fails

v1.0.0 (31Jan23)
----------------

- ENH: Surface collections as analysis subjects, so analysis functions can
  process several surfaces at once
- ENH: DOIs related to an analysis are included in downloads and shown with the
  results in the standard plot view
- ENH: The creation time of analyses is saved and shown in the task dialog
- BUG: Fixed loading of SUR files
- BUG: Fixed a problem with the name of surface collections
- MAINT: Navigation tabs can be enabled individually in the settings
- MAINT: The version information dialog shows license information
- MAINT: Improved log messages of the image creation command
- MAINT: Fixed the missing plugin list in the production Docker image
- MAINT: Removed Firefox from the production Docker image
- MAINT: Renamed "Sign in via ORCID" to "Sign in"
- MAINT: AWS access information defaults to none
- MAINT: Health checks via django-watchman, including a check of Celery
- BUILD: SurfaceTopography 1.3.3

v0.92.0 (14Dec22)
-----------------

- ENH: The bibliography (DOIs) is stored when an analysis completes
- ENH: Search also finds the names of users who created digital surface twins
  or measurements
- ENH: Search results also show the creators of unpublished digital surface
  twins and measurements
- ENH: Hovering on a data point also shows the measurement and series name
- ENH: More prominent task information, and selected analyses can be renewed
  in the user interface
- ENH: Management command that gives a user restricted admin access, to edit
  organizations or check the state of analyses
- ENH: The image creation command can process thumbnails and zoomable images
  separately and only generate missing ones
- ENH: Link to the admin interface for staff users
- ENH: Publications, and the tab with your own publications, can be disabled in
  the settings; both are enabled by default
- BUG: Fixed crashing plots when the subject's name contains an apostrophe
- BUG: Fixed a problem when a surface was part of an analysis collection
- MAINT: Figures are closed after plotting 1D measurements
- MAINT: Plugin system; statistical analyses and contact mechanics moved to
  plugins, so functionality can be added without changing the main application
- MAINT: Updated SurfaceTopography and ContactMechanics
- MAINT: Updated Django because of a security issue

v0.91.1 (19Sep22)
-----------------

- ENH: "Authors" tab on the detail page of published digital twins
- ENH: Links to the contact.engineering paper
- BUG: Renewing the bandwidth cache saves the result
- MAINT: Security updates for Django and oauthlib

v0.91.0 (05Aug22)
-----------------

- ENH: Unreliable bandwidth is shown in a different color in the bandwidth plot
- ENH: Management command to renew the bandwidth cache of all measurements,
  including the short reliability cutoff
- BUG: Fixed parallel generation of the same version numbers
- BUG: Fixed a missing import when generating thumbnails
- BUG: The import command saves to the database after updating the file name
  and before generating the compact data file
- BUG: Fixed the layout of the measurement form
- MAINT: The image creation command counts failed images as failed by default
- MAINT: Changed the intervals of the Redis health check
- MAINT: Removed old template code

v0.90.3 (27Jul22)
-----------------

- ENH: The navigation bar, including the basket, stays in place while
  scrolling
- BUG: Fixed wrong contact mechanics details
- BUG: Fixed missing progress bars for analyses that are not ready
- BUG: Fixed returning to the plot tab
- BUG: Fixed the missing download link for contact mechanics
- MAINT: SurfaceTopography 1.0

v0.90.2 (11Jul22)
-----------------

- MAINT: Faster analyses view: fewer database queries, and only plot metadata
  instead of full results is loaded when preparing plots
- MAINT: The development Docker environment creates its S3 bucket automatically
- MAINT: Security updates for Django and lxml

v0.90.1 (27Jun22)
-----------------

- MAINT: Analysis data is presigned in a separate request
- MAINT: Some optimization of database queries
- MAINT: Security fixes for numpy and flower
- MAINT: The compiled numpy package is no longer used because of a broken wheel
- MAINT: The order of analysis result cards matches the order of the chosen
  checkboxes

v0.90.0 (30May22)
-----------------

- ENH: Plots are created in the browser instead of the backend, which speeds up
  creating plots and loading data
- ENH: Buttons to hide or show data sources show the color of the data source
- ENH: Plots show the hierarchy of digital twins and measurements
- ENH: Legends of plots can be switched on and off
- ENH: Plots can be downloaded as SVG vector graphics
- ENH: The same digital twins and measurements have the same colors in all plots
- ENH: The plot legend shows the line style
- ENH: Slider for line widths in plots
- ENH: Functions are sorted by name
- ENH: Larger step size for the maximum number of iterations in contact
  mechanics
- ENH: Improved file names of downloaded containers
- BUG: Fixed labels of logarithmic scales
- BUG: Renamed the y label of the curvature distribution to probability density
- BUG: Fixed the step file name in the plot data of contact mechanics downloads
- BUG: Plastic calculations reset the plastic displacement before each
  optimizer run
- BUG: Fixed automatic redirection from http to https
- MAINT: Fixed a typo on the landing page
- MAINT: Some dependency updates because of security issues
- MAINT: Added a temporary redirect to the challenge URL

v0.20.1 (13Apr22)
-----------------

- BUG: Added a missing database migration

v0.20.0 (13Apr22)
-----------------

- BUG: A plastic system is created explicitly if a hardness is specified
- BUG: Fixed thumbnail creation and redundant thumbnail files
- MAINT: Removed the Selenium dependency; thumbnails are generated with Pillow
  and matplotlib
- MAINT: Measurement data and derived data such as thumbnails are stored under
  a unique prefix

v0.19.1 (23Mar22)
-----------------

- MAINT: Adjusted the production setup on Docker Swarm to use Redis; removed
  Memcached and RabbitMQ

v0.19.0 (23Mar22)
-----------------

- ENH: DOIs can be assigned to published datasets
- ENH: Management command for renewing containers
- ENH: Switch for the command that triggers analyses, to trigger them for all
  measurements of the given surfaces
- MAINT: Switched the cache backend and Celery broker to Redis because of
  several problems with RabbitMQ and Memcached
- MAINT: Updated Django and Pillow because of CVEs

v0.18.2 (26Jan22)
-----------------

- BUG: Fixed missing NetCDF files in the contact mechanics download
- BUG: Fixed contact calculations that stayed pending after being triggered
  manually
- BUG: Fixed a unit issue in contact mechanics for measurements with missing
  data
- BUG: The size of measurements for contact mechanics is limited
- BUG: Fixed a Memcached error
- MAINT: Workaround for failing thumbnails in production
- MAINT: Updated the Docker Swarm configuration because of connection failures
  in production

v0.18.1 (14Jan22)
-----------------

- MAINT: Added missing changes for running with the new certificate and a local
  Docker registry

v0.18.0 (14Jan22)
-----------------

- ENH: Faster display of 2D measurements and contact mechanics maps, since
  images of different detail levels are computed in advance with DeepZoom
- ENH: Improved layout of the surface list on the Find&Select tab
- ENH: Improved layout of contact mechanics analyses
- ENH: Faster access to the bandwidths of measurements, which are cached in the
  database
- ENH: Images of measurements can be created in the background with a
  management command
- ENH: Fixed the second navigation bar in place
- BUG: Fixed flaws of the progress meter for slope-dependent properties
- BUG: Fixed an insufficient number of arguments for contact mechanics
  calculations
- BUG: Fixed scheduled Postgres backups
- MAINT: The Django server no longer loads full measurements, which allows
  working with larger measurements
- MAINT: A "surface" is now called "digital surface twin"
- MAINT: Upgraded Django, Celery, lxml and Pillow because of CVEs

v0.17.0 (03Dec21)
-----------------

- ENH: Detection and optional filling of missing data points
- MAINT: The download's metadata stores the measurement size as a list instead
  of a tuple, so surfaces can be loaded with a safe YAML loader
- MAINT: Upgraded the Caddy reverse proxy in production
- MAINT: Preparations for running on Docker Swarm

v0.16.2 (15Nov21)
-----------------

- BUG: Fixed a unicode conversion issue in the OPDx reader
- BUG: Fixed a wrong condition in the command for fixing height scales
- BUG: Fixed missing permissions to start the Postgres server in the Docker
  container
- BUILD: SurfaceTopography 0.99.1

v0.16.1 (25Oct21)
-----------------

- BUG: Fixed a missing manifest entry during installation by using another
  package for Font Awesome 5 icons
- BUG: Fixed error messages when a surface analysis succeeded but none of the
  analyses of its measurements did
- BUG: Fixed a wrong import that broke the user notification command
- BUG: Fixed the alignment of 2D PSD data to 1D PSD data
- BUG: The reliability cutoff no longer removes an entire measurement
- BUG: Improved the error message for a server error in an analysis result
- BUILD: SurfaceTopography 0.98.2

v0.16.0 (18Oct21)
-----------------

- ENH: Web-like search expressions: phrases combined by AND, with OR and - for
  NOT; only measurements matching the search are shown under their surfaces
- ENH: Reliability analysis for scanning probe data
- ENH: Scale-dependent curvature
- ENH: Links to GitHub discussions
- ENH: Publication authors are shown on the Find&Select page
- BUG: The scale-dependent slope is computed with the brute force approach
- BUG: Fixed downloading analysis results with a standard error for y without
  masked values
- BUG: Missing points are shown correctly in 2D plots
- BUG: Fixed the height scale being applied twice on import
- BUG: Fixed continuing the average along x after the data is completed
- BUG: Analyses are recalculated when instrument parameters change
- BUG: Resolution and tip radius are no longer mandatory once an instrument
  type has been chosen
- MAINT: Averages are computed by SurfaceTopography
- MAINT: All properties are averaged to a reasonable number of data points
- MAINT: Analysis function names are no longer capitalized, e.g. "Roughness
  parameters"
- MAINT: Removed error bars from analysis results
- BUILD: Django 3.2, Font Awesome 5, Postgres 13.4, SurfaceTopography 0.98.0
  and ContactMechanics 0.91.0
- BUILD: Upgraded several other packages, sqlparse because of a CVE

v0.15.1 (05Aug21)
-----------------

- BUG: Removed unneeded form fields for instrument details

v0.15.0 (05Aug21)
-----------------

- ENH: Instrument details for measurements (name, type and type-specific
  parameters), to be used later for reliability analysis
- ENH: Improved layout of XLSX files with analysis data for distributions,
  power spectrum, autocorrelation, scale-dependent slope and variable bandwidth
- ENH: The usage statistics include an anonymous distribution of measurement
  uploads over users
- ENH: Support for the SPM file format, i.e. newer DI files with 32-bit data
- BUG: Unified the order of measurements in surface details and when switching
  between measurements
- BUILD: Upgraded several dependencies, e.g. SurfaceTopography 0.95.1, and
  urllib3 because of a CVE
- TST: Tests use PostgreSQL too, because of JSON fields

v0.14.0 (01Jul21)
-----------------

- ENH: Upper and lower bound of the bandwidth in the roughness parameter table
- ENH: The first column of the roughness parameter table on the "Analyze" tab is
  no longer width-limited; a horizontal scrollbar is shown instead
- ENH: Containers of published surfaces are cached on first download and can be
  downloaded directly by adding "download/" to the publication URL
- ENH: Note on how to stop the animation in the thumbnail gallery
- ENH: Management command to align measurement sizes in the database with those
  reported by SurfaceTopography
- ENH: Summary page with monthly numbers in the usage statistics; sheets are
  sorted newest first
- BUG: Fixed plots and results using the wrong measurement after changing
  fields like the detrend mode, a regression from 0.13.0
- BUG: Workaround for an exception that sometimes occurred when creating new
  measurements
- BUG: Fixed missing commas in BibTeX and BibLaTeX citations
- BUG: Fixed the statistics and output of the command for fixing height scales
- BUG: Clearer error messages for analyses of reentrant line scans, and
  "infinity" is displayed correctly in the roughness parameter table
- BUG: Improved the error message when interpolation for averaging fails; it
  names the failing measurement

v0.13.0 (16Jun21)
-----------------

- PERF: Faster upload of new measurements, by running jobs in the background
  and loading files less often
- PERF: Measurements are loaded faster from a compact data file; a management
  command recreates these files
- ENH: Publication date next to the version number in the table on the select
  page
- ENH: 1D RMS curvature for line scans and maps in the roughness parameter
  table
- ENH: Management command for fixing height scales
- BUG: Fixed failing curvature distribution for uniform line scans
- BUG: Fixed loading of 2D xyz files and incorrect scaling of OPD files
- BUG: Fixed an internal error of the contact mechanics analysis card in certain
  cases
- BUG: Fixed the count when deleting analysis functions
- BUG: Renamed the detrend mode option "Remove curvature" to "Remove curvature
  and tilt"
- ENH: Slimmer bandwidth plot for surfaces with only one measurement
- BUILD: SurfaceTopography 0.94.0 and several dependency updates for security

v0.12.0 (20May21)
-----------------

- ENH: The acquisition time in the data file, if present, is used as the
  initial measurement date after upload
- ENH: Buttons to select and deselect measurements and averages in analysis
  result plots
- PERF: The plot of a measurement loads in the background, so the page opens
  faster
- BUG: Fixed an internal server error caused by failing thumbnail generation
- BUG: Internal server errors show a friendlier page with a contact link and a
  button back to the site
- BUG: Fixed a server error when downloading PSD data for surfaces with only one
  measurement

v0.11.1 (11May21)
-----------------

- BUG: Added missing database migrations

v0.11.0 (10May21)
-----------------

- ENH: "Download" button for individual surfaces on the "Select" page
- ENH: "Download" button for all surfaces of the current selection
- ENH: Two averages can be told apart in plots when one is published, since the
  label includes the version number
- ENH: "RMS Values" is renamed "Roughness Parameters", with columns "from" and
  "symbol", more values, and numbers shown as powers of ten
- ENH: Plot axes use scientific notation with powers of 10 instead of "e"
  notation
- ENH: Colorbar labels are placed next to the colorbars
- ENH: In distribution results, the series "RMS height/slope/curvature" is
  renamed "Gaussian fit"
- MAINT: The surface container format can hold several data files per
  measurement
- BUILD: SurfaceTopography 0.93.0, Django 2.2.20, and py and
  django-debug-toolbar because of CVEs
- BUG: An average curve is shown when a surface is selected by tag only
- BUG: Fixed the command for saving default function arguments

v0.10.1 (31Mar21)
-----------------

- BUILD: The Docker image upgrades pip, so no Rust is needed to install
  cryptography

v0.10.0 (31Mar21)
-----------------

- ENH: Surface analyses average over all measurements of a surface, for power
  spectrum, autocorrelation and variable bandwidth
- ENH: New analysis function "Scale-dependent Slope", which also averages over
  a surface
- ENH: Plot tooltips show the surface name, so measurements with the same name
  can be told apart
- ENH: Widget for choosing the opacity of measurements in analysis plots
- MAINT: New users no longer get an example surface, since published surfaces
  are accessible to all users
- ENH: Surface container downloads include all metadata of surfaces and
  measurements and can hold several surfaces and licenses
- ENH: Management command for importing previously downloaded surface
  containers
- ENH: Short descriptions on the surface landing page and for the bandwidth plot
- ENH: Removed plot titles where they are not needed
- MAINT: Changed the contact email address
- BUILD: SurfaceTopography 0.92.0, which returns the nonuniform PSD only up to a
  reasonable wavevector
- BUILD: Upgraded Pillow, jinja, lxml, PyYAML, pygments and Django because of
  CVEs
- ENH: The version information shows numpy and scipy versions, which are also
  tracked for analyses

v0.9.6 (04Dec20)
----------------

- ENH: The license is displayed when viewing a published surface
- ENH: The "Recalculate" button in contact mechanics shows "Please wait" when
  pressed
- BUG: Fixed a load error in some cases when searching
- BUG: An analysis finishing after its measurement was deleted is deleted too,
  instead of causing a database error
- BUG: Fixed an error when too many measurements were selected

v0.9.5 (01Dec20)
----------------

- ENH: New layout with a menu bar instead of tabs, a selection bar below it and
  nicer vertical pills
- ENH: Counter for total requests
- BUG: Fixed the RMS table for NaN values
- ENH: Placeholder thumbnail if a thumbnail is missing
- BUG: Fixed possibly wrong versions in the contact mechanics download
- BUILD: Switched back to the original django-tagulous

v0.9.4 (23Nov20)
----------------

- ENH: New analysis function "RMS Values"
- ENH: The select tab scrolls the selected row into view
- ENH: Improved bandwidth plot without labels, with an info box on hover showing
  the name and thumbnail of the measurement
- ENH: Custom sorting of the sharing info table
- ENH: Usage statistics can be sent by email
- BUG: Fixed a wrong select tab state in the session
- ENH: Renamed the button "Properties" to "View"
- ENH: The select tab shows only the first line of descriptions; the rest
  expands on a button press
- BUG: Fixed ordering by surface name on the publication tab

v0.9.3 (12Nov20)
----------------

- BUG: Fixed XSS issues
- BUG: Fixed an issue with the command for fixing permissions

v0.9.2 (02Nov20)
----------------

- BUG: Fixed an XSS issue

v0.9.1 (02Nov20)
----------------

- BUG: Fixed missing dependencies for plotting in production

v0.9.0 (02Nov20)
----------------

- ENH: Users can publish their surfaces
- ENH: Anonymous sessions: published surfaces and analyses can be browsed
  without signing in
- ENH: Thumbnail gallery for the measurements of a surface
- ENH: Tooltips on tab headers
- BUILD: Adjusted dependencies to the new repositories split from PyCo
- BUILD: Removed the plottable dependency; the bandwidth plot uses Bokeh
- ENH: Terms and conditions version 2.0
- ENH: Anonymous counts of publication and surface views and downloads
- BUG: Fixed the display of applied boundary conditions in contact mechanics;
  results need to be recalculated
- ENH: Removed the banner saying this is a beta release

v0.8.3 (26Jun20)
----------------

- BUG: Added a missing migration for the ordering of measurements

v0.8.2 (26Jun20)
----------------

- BUG: Added missing files for tab navigation

v0.8.1 (26Jun20)
----------------

- ENH: Basket button to deselect all items
- ENH: Widget for the page size of the result table on the "Select" page
- ENH: The state of filters and paging on the Select tab is kept in the session
- ENH: Removed "back" buttons that the tabbed interface made unnecessary
- BUG: Simplified tab titles, fixing odd behavior with long titles
- ENH: Tab titles carry ">>" to show the workflow
- ENH: The "Analyze" tab only appears after pressing an "Analyze" button, which
  the basket now has too
- ENH: The contact mechanics plot replaces its interactive legend with a
  collapsed list of checkboxes, enlarging the plot area
- ENH: Replaced the loading indicator of the tree on the "Select" page
- BUG: Fixed the mail configuration in production
- BUG: Fixed overlapping pills in the detail views of surfaces and measurements
- BUG: Fixed too many tags in the tag tree when filtering
- BUG: Fixed missing tabs when displaying terms and conditions
- BUG: Fixed a wrong message in the analyses view if no analyses are available
  but items are selected
- ENH: Analyses that are about to be shown but were never triggered are
  triggered automatically
- ENH: Sharing a surface makes sure analyses with standard arguments exist for
  the user it is shared with
- BUG: The command that triggers analyses also replaces existing analyses with
  non-default arguments
- BUILD: Django 2.2.13 and markdown2 because of security issues

v0.8.0 (19May20)
----------------

- ENH: A tabbed interface replaces the links in the navigation bar and the
  breadcrumbs; the search page is now called "Select"
- ENH: The search field is in the navigation bar, so search works from anywhere
- ENH: Search runs on the server and shows results page by page
- ENH: Tags can be selected for analysis
- ENH: Removed the card in the detail views of measurements and surfaces
- ENH: The contact mechanics download includes a simple CSV file with the plot
  data
- ENH: The maximum number of iterations for contact mechanics can be set by the
  user
- BUG: Retriggering analyses no longer can result in different default
  arguments
- ENH: Management command to unify function arguments of existing analyses
- BUG: Automatic and manual step selection in contact mechanics allow the same
  number of steps

v0.7.6 (06Apr20)
----------------

- ENH: Contact mechanics pressures can be entered as a list of numbers, in
  addition to automatic selection by number of values
- BUILD: Upgraded Pillow because of security issues

v0.7.5 (27Feb20)
----------------

- ENH: Help page listing the supported file formats, with reader descriptions
  from PyCo
- ENH: The command that triggers analyses can trigger them for given functions
  or specific analyses
- ENH: Management command for sending a simple notification to all users
- ENH: More consistent orientation of measurement images, with PyCo 0.56.0
- BUG: Data files without a channel name are handled, which caused many
  exceptions and possibly too many database clients in production
- BUG: Fixed wrong units of mean and RMS in slope and curvature distributions
- BUG: Fixed loading line scans without positions
- BUILD: Django 2.2.10

v0.7.4 (14Feb20)
----------------

- ENH: Errors loading measurements that loaded before show a message and a link
  to report the issue by email
- ENH: The file format is detected only once the file has been uploaded
- ENH: Anonymous usage statistics are collected, and a daily aggregate can be
  exported with a management command
- BUG: No intermediate login page when pressing the colored boxes on the
  welcome page
- BUILD: Django 2.2.9 and PyCo 0.55.0, fixing problems with several file
  formats
- BUG: Fixed endless recursion on 404 responses, which may also have caused too
  many database connections

v0.7.3 (20Dec19)
----------------

- BUG: Fixed wrong orientation in measurement image plots
- BUG: Fixed an internal server error with existing IBW files
- BUG: Fixed white descriptions in the active row of the search list

v0.7.2 (13Dec19)
----------------

- ENH: Further usability improvements of the surface list
- ENH: Menu option to mark all notifications as read
- ENH: Tabs moved from card headers to where they apply, to make clear which
  part changes when choosing a tab
- BUG: Slashes in measurement names are replaced in XLSX sheet names
- ENH: The selection of measurements and series in the analysis view is hidden
  by default, and long names are clipped
- ENH: The contact plot shows for each point whether it converged, and its
  values, on hover
- ENH: Clicking the statistics panel jumps to the surfaces, measurements or
  sharing page
- BUILD: Upgraded Pillow because of security issues, and PyCo to 0.54.2
- BUG: The curvature distribution can be calculated for periodic surfaces
- BUG: The PSD can be calculated for nonuniform measurements again
- ENH: OPDx files can be loaded
- BUG: Measurements from HDF5 files can be flagged as periodic
- BUG: Displacement plots keep the aspect ratio
- ENH: Larger task information; measurement names that cannot be wrapped are
  shortened with an ellipsis
- BUG: Fixed the color of the "Recalculate" button and white space in the
  contact mechanics README
- ENH: The analysis results show a hint when nothing is selected yet instead of
  "Arguments for this analysis differ"

v0.7.1 (22Nov19)
----------------

- ENH: Measurements can be flagged as periodic
- ENH: Help texts explain the asterisk in forms
- ENH: Analysis downloads reference the user who uploaded each measurement file
- ENH: Unified "please wait" indicators when loading analysis results
- ENH: Notification time stamps are shown in the local time zone
- BUG: URLs to surfaces that are no longer accessible show a 403 page
- BUG: URLs to measurements that do not exist show a 404 page instead of a
  server error
- BUG: Fixed invalid links in notifications when an object is deleted
- BUG: Fixed invisible measurements in the surface list when filtering by
  category or sharing status
- ENH: Improved some visual aspects of the surface list

v0.7.0 (23Oct19)
----------------

- ENH: Surfaces and measurements can be tagged
- ENH: Hierarchical tags by inserting slashes in the tag name, e.g.
  "projects/big/part_one"
- ENH: A searchable tree lists surfaces with measurements or the tag hierarchy,
  replacing the surface cards; search covers name, description and tags
- ENH: The tree can be filtered by sharing state and category
- ENH: Checkboxes for selecting analysis functions
- BUG: Failed analyses are retriggered when requested again

v0.6.3 (07Oct19)
----------------

- BUG: Added migrations needed for the version race condition fix
- BUG: The creator of a measurement is set to empty if the uploading user is
  removed

v0.6.2 (07Oct19)
----------------

- BUG: Fixed race conditions in managing dependency versions, which stopped new
  analyses

v0.6.1 (24Sep19)
----------------

- ENH: Notifications behind a bell in the navigation bar, e.g. when a surface
  is shared or edited, or when manually triggered analyses finish
- ENH: Line scans are plotted with lines, with symbols only up to 100 points
- ENH: Analyses are kept for each combination of measurement, function and
  arguments, so known parameters show their result immediately
- BUG: Workaround for missing points in PSD plots

v0.6.0 (09Aug19)
----------------

- BUG: Fixed sheet names of the XLSX download of analysis data
- BUG: Versions of dependencies used are tracked
- ENH: "Warnings" tab instead of "Failures", with information, warnings and
  errors told apart; errors link to an email bug report with details
- ENH: The command that triggers analyses can retrigger failed ones
- BUILD: PyCo 0.51.1, which loads HDF5 and OPDX files and caches file contents
  more memory-efficiently
- ENH: An error message is shown when file contents are corrupt
- BUILD: Updated dependencies

v0.5.7 (24Jul19)
----------------

- BUG: Workaround: increased the maximum request line length
- BUG: Fixed a server error when uploading files with spaces in the file name

v0.5.6 (23Jul19)
----------------

- MAINT: The site address of the Caddy server is just the domain name

v0.5.5 (23Jul19)
----------------

- BUG: Fixed wrong heights in measurement data, using PyCo 0.32.1
- ENH: Changed buttons when editing measurements and added tooltips to the
  chevron buttons, to make batch editing clearer
- ENH: A spinner is shown whenever a point is chosen in contact mechanics
- BUG: Workaround for tooltips on multiple data points in 1D plots

v0.5.4 (16Jul19)
----------------

- BUG: Fixed a wrong height scale when units were converted on upload; size and
  unit of measurements uploaded before may be wrong
- ENH: Buttons and a menu entry to show the analyses of the surface or
  measurement being viewed

v0.5.3 (15Jul19)
----------------

- PERF: Faster PSD calculation for line scans with many data points, using
  PyCo 0.32.0
- ENH: Analysis plots use an inspect tool instead of a crosshair
- BUG: Fixed wrong messages about differing function arguments
- BUG: Permissions are checked when downloading data

v0.5.2 (12Jul19)
----------------

- PERF: Workaround for slow autocorrelation of nonuniform measurements with
  many data points
- ENH: Navigation chevron buttons also in the measurement update form

v0.5.1 (11Jul19)
----------------

- ENH: Cosmetic changes, e.g. harmonized sizes and loading behavior of opened
  surface and analysis cards

v0.5.0 (11Jul19)
----------------

- ENH: Contact mechanics analysis and visualization
- ENH: Progress bars for analysis tasks
- ENH: Old analyses for the same measurement and function are deleted
- ENH: Download of contact mechanics data
- ENH: Download of surface container archives
- BUG: Fixed wrong unit conversion in analysis plots
- BUG: Fixed a sometimes wrong target of the cancel button in the upload wizard

v0.4.2 (13Jun19)
----------------

- BUG: Added a missing template fragment that crashed the analyses view

v0.4.1 (12Jun19)
----------------

- ENH: Case-insensitive search for user names
- BUG: Fixed wrong task information on cards in the analyses view
- BUG: Empty surfaces can be selected and edited
- BUG: Fixed image plots of measurements
- BUG: Workaround for a crash when uploading a large file
- BUILD: Upgraded Celery, Bokeh, Caddy and gunicorn

v0.4.0 (28May19)
----------------

- ENH: More responsive surface list
- ENH: Progress bar when uploading a measurement file
- ENH: Statistics about shared surfaces
- ENH: Improved layout of surface search results and surface details, and an
  analysis detail view with a similar layout
- ENH: The user who uploaded a measurement is recorded
- BUG: Users can upload measurements to shared surfaces
- BUG: Fixed the target of the cancel button when editing surface details

v0.3.1 (10May19)
----------------

- BUG: Analysis results are shown for shared surfaces
- BUG: Single measurements can be selected in the surface list
- ENH: Searching for user names requires at least 3 characters
- BUG: Fixed highlighting and breadcrumb of the "Sharing" page
- ENH: Improved display of help texts in measurement forms
- ENH: Overlong breadcrumb items in the navigation bar are truncated

v0.3.0 (08May19)
----------------

- ENH: Surfaces can be shared for viewing and optionally for changing
- ENH: Users who collaborate can view and select each other's profiles
- ENH: The shares of a surface are listed in an extra tab
- ENH: A "Sharing" page in the top menu lists all shares between users
- ENH: Existing shares can be deleted or extended to allow changes
- BUG: Duplicate measurement names within a surface are prevented
- BUG: Measurements with angstrom units can be displayed in the summary plot

v0.2.0 (24Apr19)
----------------

- ENH: Surfaces have a category: experimental, simulated or dummy data
- ENH: Units are shown even if they cannot be changed
- ENH: Date pickers for measurement dates
- ENH: The surface summary sorts bandwidth bars by lower bound
- ENH: Statistics on the welcome page
- BUG: Other bug fixes

v0.1.0 (17Apr19)
----------------

- ENH: Sign-in via ORCID
- ENH: Creation of surfaces with metadata
- ENH: Upload of measurements for a surface, together with metadata
- ENH: Example surface with test data for new users
- ENH: Zooming into measurement images and line scan plots
- ENH: Automated analyses for measurements and line scans: height, slope and
  curvature distribution, power spectrum and autocorrelation
- ENH: Comparison of analysis results by overlaying plots
- ENH: Download of analysis results as PNG, XLSX or text file
- ENH: Users are asked to accept terms and conditions, optionally also further
  terms
- ENH: Storage of measurement files on an S3 backend

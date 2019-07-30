# Changelog for *TopoBank*

## 0.6.0

- fixed sheet names for XLSX download of analysis data (#39,#77)
- fixed version numbers for used dependencies, they are tracked now (#176) 

## 0.5.7

- workaround: increased limit for maximum request line (#328)
- fix for server error when uploading files with space in filename (#329)

## 0.5.6

- changed site address for Caddy server to be just the domain name

## 0.5.5

- fixed wrong heights in topography data, using PyCo 0.32.1 now (#295,#320)
- changed buttons in when editing topographies
  and added tooltips to chevron buttons in order to  make
  more clear how batch editing works (#262)
- showing a spinner every time a point is chosen in contact mechanics (#288)
- workaround for tooltips on multiple data points in 1D plot (#246) 

## 0.5.4

- fix for wrong height scale in case automated unit conversion
  was applied on upload (#290), metadata of already uploaded 
  topographies (size+unit) may be wrong
- added buttons and a menu entry to directly show analyses
  for the surface/topography the user is looking at (#264)
  
## 0.5.3

- fixes for slow PSD calculations for line scans with lots of data points,
  using PyCo 0.32.0 now (#269)
- in analysis plots, replace crosshair with inspect tool (#256,#284)
- fixes wrong messages about differing function arguments (#285,#251)
- checking now permissions when downloading data (#286)

## 0.5.2

- workaround for slow autocorrelation computation for
  nonuniform topographies with a large number of data points
- navigation chevron buttons also in topography update form

## 0.5.1

- cosmetic changes like e.g. harmonizing sizes and loading
  behavior of opened surface and analyses cards

## 0.5.0

- added contact mechanics analysis and visualization (#84)
- added progress bars for analysis tasks (#202)
- old analyses for same topography and same function will 
  be deleted (#221)
- added download of contact mechanics data (#228)
- added download of surface container archive (#48)
- fixed wrong unit conversion in analysis plots (#240)
- fixed sometimes wrong target url for cancel button in 
  upload wizard (#237)

## 0.4.2

- added missing template fragment which caused crashes in analyses view (#216)

## 0.4.1

- allow case-insensitive search for user names (#192)
- fixes wrong task information for cards in analyses view (#209)
- empty surfaces can now be selected and edited (#214)
- fixes for image plots of topographies (#76, #213)
- workaround for crash when uploading large file (#212)
- version upgrades: celery, bokeh, caddy, gunicorn

## 0.4.0

- more responsive surface list through AJAX calls (#203)
- added progress bar when uploading a topography file (#127)
- added statistics about shared surfaces (#196)
- improved layout of surface search results and surface detail view,
  added detail view for analyses with similar layout (#197,#204)
- added bookmarking the user who uploaded a topography (#181)
- fixed bug, that users couldn't upload topographies for shared surfaces (#205)
- fixed target for cancel button when editing surface details (#198)

## 0.3.1

- fixes bug that analyses results were not shown for shared surfaces (#186)
- fixes bug that single topographies couldn't be selected in surface list (#190)
- in order to find user names you have to type at least 3 characters (#184)
- fixes highlighting and breadcrumb for "Sharing" page in navigation bar (#187)
- improves display of help texts in topography forms (#180)
- added truncation for too long breadcrumb items in navigation bar (#134)

## 0.3.0

- surfaces can be shared for viewing and optionally also for changing
- user can view/select each others profiles if they collaborate, i.e. share something
- shares for a surface are listed in an extra tab
- all related shares between users are listed in a "Sharing" page accesible from top menu bar
- exisiting shares can be deleted or extended in order to allow changing a surface
- prevent duplicate topography names for same surface (fixes #91)
- topographies with angstrom units can now be display in summary plot (fixes #161)

## 0.2.0

- added category to surfaces (experimental/simulated/dummy data, #145)
- show units to users even if they cannot be changed (#149)
- added widgets for picking measurement dates (#141)
- in surface summary, sort bandwidth bars by lower bound (#85)
- added statistics on welcome page (#148)
- other bug fixes: #98

## 0.1

- login via ORCID
- creation of surfaces with metadata
- uploading topography measurements for a surface together with metadata
- example surface with test data for new users
- zoom into topography surfaces or line scan plots
- automated analyses for topographies and line scans: 
  height/slope/curvature distribution, power spectrum, autocorrelation
- compare analysis results by stitching plots
- download of analysis results as png, xlsx, or text file
- ask user for terms and conditions, also optional terms are possible
- storage of topography files on S3 backend


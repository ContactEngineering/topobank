# Changelog for *TopoBank*

## 0.9.5 (not published yet)

- new layout: menu bar instead of tabs, 
  selection bar below menu bar, nicer vertical pills (#532)
- added counter for total requests (#562)
- fix for RMS table in case of NaN values 
- added dummy thumbnail if thumbnail is missing

## 0.9.4 (2020-11-23)

- added new analysis function "RMS Values" (#445)
- autoscroll in select tab which moves selected 
  row into view (#544)
- improved bandwidth plot, removed labels
  and added info box on hover with name and 
  thumbnail of the corresponding topography (#535)
- enabled custom sorting of sharing info table (#300)
- usage statistics can be sent by email (#550)  
- fixed wrong select tab state in session (#532)
- renamed button "Properties" to "View" (#537)
- on select tab, only showing first line of 
  descriptions on load, rest expandable by 
  button press (#540)
- fixed ordering by surface name on publication tab

## 0.9.3 (2020-11-12)

- fixed XSS issues
- fixed issue with "fix_permissions" management command
  (#551)

## 0.9.2 (2020-11-02)

- fixed XSS issue

## 0.9.1 (2020-11-02)

- fixed missing dependencies for plotting in production

## 0.9.0 (2020-11-02)

- users can publish their surfaces (#317, #510, #517, #525)
- anonymous session are allowed, users can browse published
  surfaces and analyses without being signed in (#164)
- added thumbnail gallery for topographies in a surface (#514)  
- added tooltip to tab headers (#512)
- adjusted dependencies to new repositories
  resulting from splitting of PyCo package (#475)
- removed plottable dependency, using now bokeh for bandwidth 
  plot (#238) 
- added terms and conditions version 2.0 (#491)
- added anonymous counts for publication and surface
  views and downloads (#511)
- Fixing display of applied boundary conditions for contact
  mechanics calculation (#519). Recalculation needed.
- Removed banner that this is a beta release (#531)  

## 0.8.3 (2020-06-26)

- fix: added missing migration for ordering of topographies 

## 0.8.2 (2020-06-26)

- fix: added missing files for tab navigation 

## 0.8.1 (2020-06-26)

Several improvements and fixes for the user interface.

- added button to basket which allows to deselect all items (#466)
- added widget for changing page size of the result table
  on the "Select" page (#469)
- saving state of filters and paging on Select tab in session (#494)  
- removed "back" buttons not needed any more because of
  tabbed interface (#473)
- simplified tab titles, fixing strange tab behavior for 
  long tab titles (#470)
- added ">>" to tab titles in order to visualize workflow (#484)  
- tab "Analyze" is only shown if an "Analyze" button has been pressed,
  added "Analyze" button to basket (#481)
- in contact mechanics plot, replaced interactive legend by
  a collapsed list of checkboxes increasing the plot area (#472)
- replaced loading indicator for tree on "Select" page (#461) 
- fixing wrong mail configuration in production (#130, #292)
- fixing overlapping pills in detail view for surfaces and
  topographies (#471)
- fixed too many tags shown in tag tree when using filtering (#465)
- fixed missing tabs when displaying terms and conditions (#474)
- fixed wrong message in analyses view if no analyses available,
  but some items have been selected (#485)
- if analyses are about to be shown which have not been triggered yet,
  these analyses are triggered automatically (#402)
- when sharing a surface, it is assured that analyses for the standard arguments
  of all automatic functions are available for the user the surface is
  shared with (#388)
- fixed bug in management command "trigger_analyses", now also replaces
  existing analyses with other arguments than default arguments (#447)
- update to Django 2.2.13 because of security issues (#488)
- updated markdown2 dependency because of security issue (#458)

## 0.8.0 (2020-05-19)

This release mainly implements a redesign of the user interface.

- replaced links in navigation bar and breadcrumbs 
  by tabbed interface (#370, #463, #462), search page is
  now called "Select"
- search field is placed in the navigation bar, search can be
  done from everywhere (#419)
- search is done servers-side, result is shown page by page (#418, #380)
- tags can also be selected for analysis        
- removed card in detail view of topography and surface (#422)
- added simple CSV file with plot data in the ZIP archive
  when downloading data from contact mechanics calculations (#459)
- maximum number of iterations for contact mechanics calculations 
  can be specified by the user (#460)
- fixed that retriggering of analyses could result in different
  default arguments (#457)
- added management script to unify function arguments for exisiting
  analyses (#468)
- fixed different number of allowed steps for automatic and manual
  step selection in contact mechanics calculations (#455)

## 0.7.6 (2020-04-06)

- contact mechanics: added option for manual pressure selection by entering a 
  list of numbers (in addition to automatic pressure selection given the number 
  of values, #452)
- upgrade of Pillow library because of security issues (#454)

## 0.7.5 (2020-02-27)

- added help page with supported file formats, descriptions for the readers
  are defined in PyCo (#424)
- management command 'trigger_analyses' now can trigger analyses also 
  for given functions or specific analyses
- added management command 'notify_users' for sending a simple notification 
  to all users (#437)
- more consistent orientation of topography images,
  including an upgrade to PyCo 0.56.0 (#440)
- more robust when no channel name was given in data file (#441),
  this seemed to generate a lot of exceptions in production
  maybe resulting in too many database clients (#436)
- fix for wrong units of special values (mean+rms) of slope and 
  curvature distributions (#444)
- fix for problem when loading line scans without position (#446)
- upgrade to Django 2.2.10 (#439)

## 0.7.4 (2020-02-14)

- problems during loading of topographies which could already
  be loaded earlier now show error message and a mailto link
  in order to report the issue (#416)
- format detection is only done once file has been uploaded (#412)
- added collection of anonymous usage statistics in local database
  (#147, #427, #431); a non-personal overview with aggregated values per day
  can be exported via the management command "export_usage_statistics" 
- make sure there is no intermediate login page when pressing
  on colored boxes on welcome page (#423)
- upgrade to Django 2.2.9 (#417) 
- upgrade to PyCo 0.55.0 (#428), this fixes problems with
  various file format (see PyCo's changelog for details)
- fix for endless recursion on 404 responses (#367), should also
  fix problems with too many database connections (#436)
  
## 0.7.3 (2019-12-20)

- fixes wrong orientation in topography image plots (#253,#378)
- fixes internal server error with existing ibw files (#413)
- fixes white description in active row of search list (#414)

## 0.7.2 (2019-12-13)

- further improvements on the usability of the surface list (#381)
- added menu option to mark all notifications as read (#391)
- removed tabs from card headers and shifted them as tabs
  to relevant places in order to make clear which part changes
  when choosing another tab (#372) 
- replace / in sheet names before saving xlsx from analyses (#77),
  was closed already but we forgot slashes in topography names
- hide selection of topographies and series in analysis view by 
  default (#310, #404); also clip too long topography names here
- in contact plot, show for each point a small over showing 
  whether a point properly converged or not, as well as values 
  from the axes (#297, #406)
- jump to surfaces, topographies or sharing page when clicking 
  the statistics panel (#248) 
- upgraded pillow package which had security issues (#400)
- upgraded PyCo package to version 0.54.2
- fix that curvature distribution can be calculated for
  periodic surfaces (#382)
- fix for missing "is_periodic" in pipeline which made e.g. that    
  PSD couldn't be calculated nonuniform topographies (#409) 
- OPDx files can now be loaded (#325)  
- fix for topographies from HDF5 files which could't be flagged 
  as periodic (#399)   
- match aspect ratio in displacement plots (#277)
- made task information larger, topography names which cannot
  be broken down to lines are now limited by ellipsis (#252)  
- fixes color of "Recalculate" button (#405)   
- removed unneeded white space in contact mechanics' README file
- don't show "Arguments for this analysis differ" in analyses results
  if nothing is selected; instead, show an info box that no surfaces 
  and topographies have been chosen yet (#408)
   
## 0.7.1 (2019-11-22)

- added "is_periodic" flag for topographies (#347)
- added help texts explaining the asterisk in forms (#305)
- added reference to analyses' download files which user has
  uploaded a topography file (#188)
- unified "please wait" indicators when loading analysis results by AJAX (#236)
- showing notification time stamps now in local time zone
- showing now 403 page if entering a URL which tries to
  access a surface which is no longer accesible
- showing now 404 page also for topography urls which do not exist
  (before server error) 
- fixed invalid links in notifications when an object is deleted (#363)
- fixed invisible topographies in surface list when filtering for category/sharing status (#376)
- improved some visual aspects in surface list (#381, not finished yet)
 
## 0.7.0 (2019-10-23)

- surfaces and topographies can now be tagged (#52)
- hierachical tags can be used when inserting slashes in the tag name, 
  e.g. "projects/big/part_one" (#266)
- replaced view of surfaces by cards with a tree widget, either listing
  all surfaces with topographies, or listing all top level tags which build 
  the main branches of a tag tree; all entries can be searched by name,
  description and tags (#304,#266)  
- search tree can be filtered by sharing state and category (#185)   
- using checkboxes for selecting analysis functions (#271)
- failed analyses are retriggered now when requested again (#371)

## 0.6.3 (2019-10-07)

- added migrations needed for bug fix (#366)
- fixed setting of topography creator to NULL if uploading user
  is removed

## 0.6.2 (2019-10-07)

- bug fix for race conditions while managing dependency versions,
  stopped new analyses (#366)
  
## 0.6.1 (2019-09-24)

- added notifications through a "bell" symbol in the navigation bar
  (#26,#332); notifications are stored in the database and shown 
  to a logged-in user; they're triggered by these events:
   
  + a surface is shared or unshared with the current user 
  + a user gets change access to a surface
  + a shared item was edited
  + a collection of analyses, which has been manually triggered
    has been finished
  + an example surface was created on first login
           
- plotting now line scans with lines; symbols are also used
  if no more than 100 points (#312)
- internal change: analyses are now saved for every combination of topography,
  function and arguments; for each user a specific combination
  is shown; one benefit is if user selects already known parameters,
  the result is immediately there (#208)
- workaround for missing points in PSD plots (#356)   
  
  
## 0.6.0 (2019-08-09)

- fixed sheet names for XLSX download of analysis data (#39,#77)
- fixed version numbers for used dependencies, they are tracked now (#176)
- tab "Warnings" instead of "Failures", incompatible topographies
  for an analysis function is shown as information in a blue box;
  hint about translucent points are shown as warning in a yellow box;
  exceptions in analyses are now shown as error, together with a link
  which makes it easy to send a bug report as e-mail with detailed 
  information (#230)
- extended management command "trigger_analyses" such that failed
  analyses can be retriggered
- ported backend to use newer PyCo version 0.51.1 (#289),
  among other things this release allows to load HDF5 files (302) 
  and OPDX files (#325), more memory efficient caching of file
  contents 
- now shows an error message when file contents are corrupt
- updated dependencies  
  
   
## 0.5.7 (2019-07-24)

- workaround: increased limit for maximum request line (#328)
- fix for server error when uploading files with space in filename (#329)

## 0.5.6 (2019-07-23)

- changed site address for Caddy server to be just the domain name

## 0.5.5 (2019-07-23)

- fixed wrong heights in topography data, using PyCo 0.32.1 now (#295,#320)
- changed buttons in when editing topographies
  and added tooltips to chevron buttons in order to  make
  more clear how batch editing works (#262)
- showing a spinner every time a point is chosen in contact mechanics (#288)
- workaround for tooltips on multiple data points in 1D plot (#246) 

## 0.5.4 (2019-07-16)

- fix for wrong height scale in case automated unit conversion
  was applied on upload (#290), metadata of already uploaded 
  topographies (size+unit) may be wrong
- added buttons and a menu entry to directly show analyses
  for the surface/topography the user is looking at (#264)
  
## 0.5.3 (2019-07-15)

- fixes for slow PSD calculations for line scans with lots of data points,
  using PyCo 0.32.0 now (#269)
- in analysis plots, replace crosshair with inspect tool (#256,#284)
- fixes wrong messages about differing function arguments (#285,#251)
- checking now permissions when downloading data (#286)

## 0.5.2 (2019-07-12)

- workaround for slow autocorrelation computation for
  nonuniform topographies with a large number of data points
- navigation chevron buttons also in topography update form

## 0.5.1 (2019-07-11)

- cosmetic changes like e.g. harmonizing sizes and loading
  behavior of opened surface and analyses cards

## 0.5.0 (2019-07-11)

- added contact mechanics analysis and visualization (#84)
- added progress bars for analysis tasks (#202)
- old analyses for same topography and same function will 
  be deleted (#221)
- added download of contact mechanics data (#228)
- added download of surface container archive (#48)
- fixed wrong unit conversion in analysis plots (#240)
- fixed sometimes wrong target url for cancel button in 
  upload wizard (#237)

## 0.4.2 (2019-06-13)

- added missing template fragment which caused crashes in analyses view (#216)

## 0.4.1 (2019-06-12)

- allow case-insensitive search for user names (#192)
- fixes wrong task information for cards in analyses view (#209)
- empty surfaces can now be selected and edited (#214)
- fixes for image plots of topographies (#76, #213)
- workaround for crash when uploading large file (#212)
- version upgrades: celery, bokeh, caddy, gunicorn

## 0.4.0 (2019-05-28)

- more responsive surface list through AJAX calls (#203)
- added progress bar when uploading a topography file (#127)
- added statistics about shared surfaces (#196)
- improved layout of surface search results and surface detail view,
  added detail view for analyses with similar layout (#197,#204)
- added bookmarking the user who uploaded a topography (#181)
- fixed bug, that users couldn't upload topographies for shared surfaces (#205)
- fixed target for cancel button when editing surface details (#198)

## 0.3.1 (2019-05-10)

- fixes bug that analyses results were not shown for shared surfaces (#186)
- fixes bug that single topographies couldn't be selected in surface list (#190)
- in order to find user names you have to type at least 3 characters (#184)
- fixes highlighting and breadcrumb for "Sharing" page in navigation bar (#187)
- improves display of help texts in topography forms (#180)
- added truncation for too long breadcrumb items in navigation bar (#134)

## 0.3.0 (2019-05-08)

- surfaces can be shared for viewing and optionally also for changing
- user can view/select each others profiles if they collaborate, i.e. share something
- shares for a surface are listed in an extra tab
- all related shares between users are listed in a "Sharing" page accesible from top menu bar
- exisiting shares can be deleted or extended in order to allow changing a surface
- prevent duplicate topography names for same surface (fixes #91)
- topographies with angstrom units can now be display in summary plot (fixes #161)

## 0.2.0 (2019-04-24)

- added category to surfaces (experimental/simulated/dummy data, #145)
- show units to users even if they cannot be changed (#149)
- added widgets for picking measurement dates (#141)
- in surface summary, sort bandwidth bars by lower bound (#85)
- added statistics on welcome page (#148)
- other bug fixes: #98

## 0.1 (2019-04-17)

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


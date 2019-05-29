# Changelog for *TopoBank*

## 0.5.0

- fixes wrong task information for cards in analyses view (#209)

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


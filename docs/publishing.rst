Publishing Data
===============

Publishing is a non-reversible action which gives all users of the application
read access to a surface.

Comparison with Sharing
-----------------------

Sharing is for *collaboration*. It is implemented since version 0.4.

A share ..

- can be withdrawn later,
- optionally allows to change a surface,
- is given individually.

Publishing is different from sharing in many aspects:

- A publication cannot be withdrawn.
- A published surface cannot be changed any more.
- A published surface and all its data cannot be removed.
- Everyone can see and download the published data.

Because of these differences, *publishing* should be clearly distinct from *sharing* in the user interface.

Both have in common, that another user can see and download all data
and can perform analyses probably with new parameters.

The analyses are **not** part of the shared or published data, so every user can restart analyses with different
parameters as usual.


User Interface
--------------

The user interface for version 0.9.0 should be extended by these elements:

- The properties page of a surface should show an extra button "Publish..." in another
  color like "Delete..". Then a "Publish" tab opens.
- The "Publish" tab should inform the user that the published surface and all its data
  cannot be changed nor removed and everyone can see and download the data.
- The "Publish" tab should ask the user for a license: CC0, CC BY, CC BY-SA
  The user must choose a license.
- Before publishing the user is asked if he's really sure, or if he want to cancel and double-check.
- Besides the "sharing tab", every user has also a "published" tab (icon: "bullhorn") which lists the
  data sets published by this user, similar as in the sharing tab
- Properties: When looking at the properties of a shared surface, there is no "Edit" or "Delete" button for everyone
- Properties: There is a badge showing "published" for the owner and "published by ..." for anyone else
- Properties: The permissions also lists "Everyone" with "read" access, it is the only line here.
  Also link to "published" tab if published items are listed.
- On the "Select" tab, the published surfaces are listed as well; there is another filter option
  "Only published surfaces". The filter option "Only surfaces shared with me" may be changed to
  "Only surface shared with me explicitly"
- When downloading a published surface, a license file should be included.
- When downloading analysis of a published surface, a license file should be included.
- The help page should explain sharing and publishing.
- For publishing, the surface must have at least one topography.


Duplicate and Versioning
------------------------

Internally, in order to publish a surface, it is automatically internally copied
from the original surface, with all metadata, data files, topography meta data.
The standard analysis function are then triggered for this new surface.

The original surface is kept unchanged.
For the new surface the only permissions are that everyone can view it.
No user can change or delete it. It has a pointer to the original surface.

Whenever the new surface is published, it is a new version of the original surface.
These published versions build a linear chain.
The chain links have version numbers 1,2,3,..

Permanent URL
-------------

There is a permanent URL for the published surfaces, in the form
```
    https://contact.engineering/go/<UIID>
```
This redirects to the property page of the surface.

Each specific version of a surface gets an new URL.

Implementation in Backend
-------------------------

Every user is member of the group "all". When a surface is published, it is copied
with all topographies, topography files and metadata from surface and topographies.
The group "all" is granted "read" access for this copy. No other permissions are added
especially no edit or delete permissions. The original surface is kept like it is.
It can still be shared, changed or deleted.

Additionally, an entry in a "publication list" is created for the copy.
That entry has a pointer to the surface and also has the version number,
a timestamp, a UUID for the URL and a publisher.
Later this list can also serve for other permanent URLs.

All surfaces get a pointer to an *original surface* which is NULL by default.
For the copy after publication, it points to the original surface.
Like this, all versions for a surface (published or "current") can be accessed.

Outlook
-------

An anonymous user should also be able to view a published surface without log in.

Later this could be extended by automatically registering a DOI with this surface.
Then the URL for this DOI should point into this application.

Notes about DOIs
----------------

[Zenodo](https://zenodo.org/) has a [REST API](http://developers.zenodo.org/) and could be an option
which allows us to easily publish datasets with a DOI.
There are already many useful metadata fields.
Also our software could be published there, so we could publish analysis results along with the code.
Zenodo is financed by the European Commission and open for everybody doing research worldwide.





Publishing Data
===============

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
- Besides the "sharing tab", every user has also a "published" tab (icon: "bullhorn") which lists the published
  datasets, these are links like in the sharing tab
- OR: the published datasets are listed in the sharing tab, but without checkbox (nothing can be changed)
  and with "published" flag
- When looking at the properties of a shared surface, there is no "Edit" or "Delete" button for everyone
- On the "Select" tab, the published surfaces are listed as well; there is another filter option
  "Only published surfaces". The filter option "Only surfaces shared with me" may be changed to
  "Only surface shared with me explicitly"
- When downloading a published surface, a license file should be included.
- When downloading analysis of a published surface, a license file should be included.


Implementation in Backend
-------------------------

Every user is member of the group "all". When publishing, the group "all" is granted
"read" access. At the same time, "edit" and "delete" permissions are removed for all users.
Additionally, the surface gets a "published" flag in the database.








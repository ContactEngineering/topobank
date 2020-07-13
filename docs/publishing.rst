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
- After publishing, all users should get a notification about the published surface.
- For publishing, the surface must have at least one topography.


Implementation in Backend
-------------------------

Every user is member of the group "all". When publishing, the group "all" is granted
"read" access. At the same time, "edit" and "delete" permissions are removed for all users.
Additionally, the surface gets a "published" flag in the database.


Outlook
-------

More ideas:

There is a permanent URL with slug for published surfaces, e.g.
"https://contact.engineering/publications/contact-challenge" or using a UUID.
This could redirect to the internal property page.

An anonymous user should also be able to view a published surface without log in.

Later this could be extended by automatically registering a DOI with this surface.
Then the URL for this DOI should point into this application.

Notes about DOIs
----------------

Publication could make use of DOIs and/or probably directly at the ORCID account, see

http://support.orcid.org/knowledgebase/articles/116739-register-a-member-api-client-application

ORCID has a *public API*, which can be used to authenticate researches and to get some public records, and a *member API* which could be used to update the ORCID record of a researcher automatically: https://support.orcid.org/hc/en-us/articles/360006972533-What-s-the-difference-between-the-Public-and-Member-APIs-

[Zenodo](https://zenodo.org/) has a [REST API](http://developers.zenodo.org/) and could be an option which allows us to easily publish datasets with a DOI. There are already many useful metadata fields. Also our software could be published there, so we could publish analysis results along with the code. Zenodo is financed by the European Commission and open for everybody doing research worldwide.





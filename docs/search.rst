
Searching topographies and surfaces
===================================

Filter controls
---------------

Global search field
^^^^^^^^^^^^^^^^^^^

The global search field is part of the top navigation
bar and always visible inside the application.

The search term is a string which is searched for in
names, descriptions and tags
of all topographies and surfaces.

If a search term was entered on any page of the application,
the "Select" page should be loaded with a surface tree,
with no restriction on category and sharing status (showing "own" surfaces
as well as "shared" surfaces).

Category filter control
^^^^^^^^^^^^^^^^^^^^^^^

This is a dropdown element on the "Select" page.
When selecting another category, the page is reloaded such that
only surfaces are included which match the given category.

The category is a propery of each surface. The control
allows the follwing options:

- *Experimental data only*
- *Simulated data only*
- *Dummy data only*
- *All categories* (no restriction)

If the user selected the "tag tree" view before changing
this control, he should stay on tag tree view.

Sharing status filter control
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This is a dropdown element on the "Select" page.
When selecting another sharing status, the page is reloaded such that
only surfaces are included which match the given sharing status.

The control allows one of the following values

- *Only own surfaces*
- *Only surfaces shared with the current user*
- *Own and shared surfaces* (no rectriction)

If the user selected the "tag tree" view before changing this
filter, he should stay on tag tree view.


Definition of matches
---------------------

Surface match
^^^^^^^^^^^^^

A *surface matches*, if

- it has the search term in the name, or
  in its description or in an associated tag, and
- its category matches the category of the category filter, and
- its sharing status matches the sharing status filter

Topography match
^^^^^^^^^^^^^^^^

A *topography matches*, if

- it has the search term in the name, or
  in its description or in an associated tag, and
- the category of its surface matches the category of the category filter, and
- the sharing status of its surface matches the sharing status filter

Tag match
^^^^^^^^^

A tag matches, if

- it has the search term in its name

Two different tree views
------------------------

The user can select between two different tree views
of the search results.

Surface tree
^^^^^^^^^^^^

In the surface tree view, the surfaces are on top level,
the topographies are the leaves. There can be also empty surfaces.

The surface tree should be comprised of

- all surfaces which match - for these surfaces, all topographies should be shown
  underneath
- all surfaces having at least one topography which matches - if the surfaces itself
  does not match, then only those topographies which match should be shown
  underneath

Tag tree
^^^^^^^^

The tag tree has tags at its top levels and can be
several levels deep, depending on the tag hierachy (eg. "food/fruits/apple").
The leaves are surfaces and topographies having these tags.
So one surface or topography can appear more than once in the
tag tree.

The tag tree should be comprised of

- all surfaces which match including their parent tags,
  for those surfaces all topographies should be shown
- all surfaces having a topography which matches, if the surfaces itself
  does not match, then only those topographies which match should be shown
  underneath



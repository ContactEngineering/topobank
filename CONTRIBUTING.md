Contributing to TopoBank
========================

Code style
----------
Always follow [PEP-8](https://www.python.org/dev/peps/pep-0008/) with the exception of line
breaks.

Development branches
--------------------
New features should be developed always in its own branch. When creating your own branch,
please suffix that branch by the year of creation on a description of what is contains.
For example, if you are working on an implementation for line scans and you started that
work in 2019, the branch could be called "19_line_scans".

Commits
-------
Prepend you commits with a shortcut indicating the type of changes they contain:
* BUG: Bug fix
* BUILD: Changes to the build system
* CI: Changes to the CI configuration
* DEP: Update in 3rd-party dependencies
* DOC: Changes to documentation strings
* ENH: Enhancement (e.g. a new feature)
* MAINT: Maintenance (e.g. fixing a typo)
* TST: Changes to the unit test environment
* WIP: Work in progress

API design
----------
* No nested serialization: Exceptions are tags and properties
* Each API response has a `url` field that points to itself
* Each API response has an `id` field that returns the internal id (and is 
  potentially redundant to `url`)
* URLs pointing to other API resources are suffixed by `_url`
* Auxiliary API endpoints are in a nested dictionary `api`. Those entries are
  not suffixed with `_url`.
* Use Pythonic `snake_case` for the whole API


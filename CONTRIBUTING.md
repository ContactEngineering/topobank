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
work in 2018, the branch could be called "18_line_scans".

Commits
-------
Prepend you commits with a shortcut indicating the type of changes they contain:
* ENH: Enhancement (e.g. a new feature)
* MAINT: Maintenance (e.g. fixing a typo)
* DOC: Changes to documentation strings
* BUG: Bug fix
* TST: Changes to the unit test environment
* CI: Changes to the CI configuration
* WIP: Work in progress
* DEP: Update in 3rd-party dependencies

User-interface guidelines
-------------------------
* Use explicit, descriptive buttons and links. Do not use icons only.

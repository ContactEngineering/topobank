Analyses
========

Each analysis is saved as an entry in the Analysis table.
The entries should be unique for a given set of function arguments, 'kwargs'
(db: field 'kwargs', pickeled), and 'function' (db: field 'function_id') and 'topography'
(db: field 'topography_id').

Each analysis has also a set of 'users' which indicate, which users will see this analysis.
If an analysis is requested by a user which already exists, this analysis will be
altered by simply putting the user on its list.
If the analysis does not exist yet, it is created and the 'users' just points to
the requesting user. This analysis can also be taken then if requested by other users later.




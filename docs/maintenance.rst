Maintenance
===========

.. role:: bash(code)
   :language: bash

Management Commands
-------------------

`grant_admin_permissions`
.........................

Call this with a username as argument in order to grant permissions for
using the admin interface. In order to find out the username,
you can either use an existing admin access or enter the "User profile"
page in the application. Then you can see your username in the URL.

Example:

    The URL is `https://contact.engineering/users/michael/`, then the username is `michael`.

After granting the permission, you can enter the admin page. The link
can be found by this user in the menu item which is named after the user.

Currently only a subset of models can be changed and seen via the admin.
The user can create and change organizations and view, filter and delete
analyses.

The main reason for enabling this access is to
- investigate into problems with analyses
- create new organizations
- grant plugin permissions for individual organizations

`export_usage_statistics`
.........................

Call this in order to get an Excel file with basic anonymous usage statistics, e.g.:

.. code:: bash

    docker-compose -f production.yml run --rm django python manage.py export_usage_statistics

In the toplevel directory, an Excel file "usage_statistics.xlsx" is generated.

I order to copy the file to the local file system, you can do

.. code:: bash

    docker cp topobank_django_1:app/usage_statistics.xlsx docker_stats.xlsx

(before use `docker ps` in order to find out the container's name).

`list_workflow_schemas`
.......................

List all registered workflows together with the JSON schema and the default
values of their keyword arguments (parameters). Useful when adjusting clients
(e.g. the frontend) to changed workflow parameters.

.. code:: bash

    python manage.py list_workflow_schemas

Options:

- ``--name <workflow>`` — only show the workflow with this registry name,
  e.g. ``--name topobank_statistics.power_spectral_density``.
- ``--json`` — emit a machine-readable JSON document on stdout.
- ``--output <file>`` — write the JSON document to a file instead of stdout
  (implies ``--json``); use this when log handlers write to stdout and would
  corrupt piped output.
- ``--indent <n>`` — indentation level for JSON output (default: 2).

Each entry contains ``name``, ``display_name``, ``kwargs_schema`` (the
Pydantic-generated JSON schema of the parameter model) and ``default_kwargs``
(the parameter defaults as a dictionary).


Monitoring
----------

`How much analyses are pending?`
................................

One possibility is to enter an ipython shell, either on the Container
on your laptop during development and run

.. code:: python

    while True: print({ s:Analysis.objects.filter(task_state=s).count() for s in ['su','pe','fa','st']}); import time; time.sleep(2)



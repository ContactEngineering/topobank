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
you can either use an existing admin access or enter the "User Profile"
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


Monitoring
----------

`How much analyses are pending?`
................................

One possibility is to enter an ipython shell, either on the Container
on your laptop during development and run

.. code:: python

    while True: print({ s:Analysis.objects.filter(task_state=s).count() for s in ['su','pe','fa','st']}); import time; time.sleep(2)



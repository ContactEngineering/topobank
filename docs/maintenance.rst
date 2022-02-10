Maintenance
===========

.. role:: bash(code)
   :language: bash

Management Commands
-------------------

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



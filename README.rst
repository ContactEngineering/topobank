TopoBank
========

Topography Storage and Calculation Service for Contact Mechanics.

.. image:: https://img.shields.io/badge/built%20with-Cookiecutter%20Django-ff69b4.svg
     :target: https://github.com/pydanny/cookiecutter-django/
     :alt: Built with Cookiecutter Django


Settings
--------

Moved to settings_.

.. _settings: http://cookiecutter-django.readthedocs.io/en/latest/settings.html

User Accounts
-------------

The application uses `ORCID`_ for user authentication, so you need an ORCID account to use it.

If you need a super user or staff user during development, e.g. for acccessing the admin page,
connect to the datbase and set the :code:`is_superuser` or :code:`is_staff` flags manually.

.. _ORCID: https://orcid.org/

Running tests with py.test
--------------------------

::

  $ USE_DOCKER=no DJANGO_SETTINGS_MODULE=config.settings.test pytest

Or use run configurations in your IDE, e.g. in PyCharm.

Docker
------

The full application can be run in Docker containers, for development and production.
This also includes the database, message brokers, celery workers and more. It is currently the easiest way
to run the full stack.

See the Sphinx documentation how to install docker and how to start the application using docker,
for deployment (see chapter "Deploy") or local development
(see "Installation on development machine / Starting Topobank in Docker").


Celery
------

This app comes with Celery.

To run a celery worker:

.. code-block:: bash

    cd topobank
    celery -A topobank.taskapp worker -l info

Please note: For Celery's import magic to work, it is important *where* the celery commands are run. If you are in the same folder with *manage.py*, you should be right.

There is a bash script :code:`start-celery.sh` which also sets some environment variables needed in order to connect to the message broker
and to the result backend.

Funding
-------

Development of this project is funded by the `European Research Council <https://erc.europa.eu>`_ within `Starting Grant 757343 <https://cordis.europa.eu/project/id/757343>`_.

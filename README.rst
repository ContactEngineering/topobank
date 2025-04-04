TopoBank
========

A surface metrology cloud database.

User Accounts
-------------

The application uses `ORCID`_ for user authentication,
so you need an ORCID account to use it.

If you need a super user or staff user during development, e.g. for acccessing the admin page,
connect to the database and set the :code:`is_superuser` or :code:`is_staff` flags manually.

.. _ORCID: https://orcid.org/

Running tests with pytest
-------------------------

You need a PostgreSQL database to run tests.

::

  $ pytest

Or use run configurations in your IDE, e.g. in PyCharm.

Linting with pre-commit hooks
-----------------------------

We are testing the code quality in the test pipeline, if your code is not conform with flake8,
the pipeline will fail.
To prevent you from committing non-conform code, you can install pre-commit.
`pre-commit` runs tests on your code befor the commit.
Just install `pre-commit` with pip or your package manager.
Then run:

.. code-block:: bash

    pre-commit install

That is all you really need to do!

To run the `pre-commit` hooks by hand you can run:

.. code-block:: bash

    pre-commit run

If you want to skip a pre-commit stage, i.e. flake8, run:

.. code-block:: bash

   SKIP=flake8 pre-commit run

Docker
------

The full application can be run in Docker containers, for development and production.
This also includes the database, message brokers, celery workers and more. We maintain a
`full development stack <https://github.com/ContactEngineering/topobank-stack-development>`_
that uses docker. The develoment stack is currently the simplest way to run TopoBank on
your local machine.

Celery
------

This app comes with Celery. To run a celery worker:

.. code-block:: bash

    cd topobank
    celery -A topobank.taskapp worker -l info

Please note: For Celery's import magic to work, it is important *where* the celery commands are run. If you are in the same folder with *manage.py*, you should be right.

There is a bash script :code:`start-celery.sh` which also sets some environment variables needed in order to connect to the message broker
and to the result backend.

API documentation
-----------------

API documentation is exposed at the URL: api/schema/swagger-ui/

Funding
-------

Development of this project was funded by the `European Research Council <https://erc.europa.eu>`_ within `Starting Grant 757343 <https://cordis.europa.eu/project/id/757343>`_.

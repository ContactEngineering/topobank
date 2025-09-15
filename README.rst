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

You need a PostgreSQL database to run tests. See next section on how to setup a PostgreSQL database.

::

  $ pytest

Or use run configurations in your IDE, e.g. in PyCharm.

Postgres configuration
----------------------

The simplest setup that works across operating systems is to run a
PostgresSQL database in a Docker container. Simply run

.. code-block:: bash

    docker run --name postgres -p 5432:5432 -e POSTGRES_HOST_AUTH_METHOD=trust -d postgres:17.6

to run Postgres. Note that you only need to execute the above command once. You can
then start or stop the service through `docker start postgres`, `docker stop postgres`
or from your IDE. (Both PyCharm and Visual Studio Code can control Docker.)

If you run through docker, you need to speciy the database settings when running
pytest. Execute

.. code-block:: bash

    DATABASE_URL=postgres://postgres@localhost/topobank-test pytest

to tell Django where to find the database.

On macOS another solution is to download the official Posgres app and run Postgres from there.
The `DATABASE_URL` does not need to be specified in this case. (The default works.)

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

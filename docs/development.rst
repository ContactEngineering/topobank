
Development
===========

Use a virtual environment
-------------------------

For everything listed here, use a virtual environemt,
which can be generated e.g. via

.. code:: bash

    python -m venv ./venv

in the project's main directory. Activate with

.. code:: bash

    . venv/bin/activate

How to update requirements
--------------------------

The requirements are defined in :code:`setup.cfg`.
Under :code:`install_requires = ` everything is listed
for running the application in production.
In the section

.. code::

    [options.extras_require]
    dev =

all additional dependencies are listed which are needed for development.

In order to generate requirements files, which are used e.g. in the Docker files, enter
the :code:`requirements` directory and call :code:`make`.
Make sure the virtual environment is activated.

Afterwards, the local environment can be updated using

.. code:: bash

    $ pip install -r requirements/local.txt

Setup use of docker compose
---------------------------

For configuring :code:`docker compose`, copy the template file
:code:`.env.template` to :code:`.env`.
Then insert here

.. code::

    TOPOBANK_UID=<insert here your user id>
    TOPOBANK_GID=<insert here your group id>

your user and group id. By doing this, the files in the django
container will have the same IDs as you have and you can access them easily.
Also the internal `pypi` server is run with the same IDs.


Building plugin packages
------------------------

.. code:: bash

    $ python -m build .

The package files are generated in the :code:`dist/` directory.

They can be uploaded to the local repository, e.g. by using :code:`twine`,
if the local pypi server is running by docker-compose.

.. code:: bash

    $ twine upload -r localpypi dist/* --verbose

Twine uses a local config file :code:`~/.pypirc`, which has an entry like this:

.. code::

    [localpypi]
    repository = http://localhost:8010
    username = topobank
    password = topobank

Updating plugins when using Docker
----------------------------------

When building the local Docker image for development using

.. code:: bash

    $ docker-compose -f local.yml build

the plugins listed in :code:`requirements/plugins.txt` are installed.

If you need the code of a plugin running in Docker and you are currently
developing this plugin:
First build the plugin package, upload it to the integrated pypi server (see above)
and rebuild the image, then restart the docker containers.

Accessing Minio contents from localhost
---------------------------------------

If you run the application in Docker with :code:`docker compose -f local.yml up`,
you want your browser to be able to access the S3 contents directly,
because the Zoom image of a measurement and also the analyses results are fetched from
there without going over the django application server.

In order to do so, we use a trick:

1. Edit your :code:`/etc/hosts` and add this line:

.. code::

    127.0.0.1 topobank-minio-alias

2. Make sure in :code:`.envs/.local/.django` that you have configured

.. code::

   AWS_S3_ENDPOINT_URL=http://topobank-minio-alias:9000

3. Make sure that in :code:`local.yml` you define an alias for the :code:`minio` container
   e.g.

   .. code::

    networks:
      topobank_net:
        aliases:
          # For localhost access, add the following to your /etc/hosts
          # 127.0.0.1  topobank-minio-alias
          # and make sure that in settings, the AWS URL also uses this hostname;
          # Like this, the URL given for accessing the S3 can be resolved
          # on the host computer, because minio is exposed to port 9000 on host
          - topobank-minio-alias

    Of course you need to use this network :code:`topobank_net` also for this other containers
    and define it on top.

The alternative we used before is also possible. You could also
defined in :code:`/etc/hosts` an alias the the **current IP of minio**, e.g.

.. code::

    172.18.0.5      minio

The current minio IP can be found be inspecting the running minio service.
This has to be changed each time the minio IP changes, so this is a bit cumbersome.















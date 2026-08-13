
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

Accessing S3 contents from localhost
------------------------------------

The browser accesses some S3 contents directly, without going through the Django
application server: the zoom image of a measurement and the analysis results are
fetched from the storage backend. The S3 endpoint therefore has to be reachable
under the same URL from both the application server and the browser.

Configuring URL resolution
..........................

The development stack (see :code:`ce-devbox`) runs SeaweedFS as a normal process
on the development machine, so both the application server and the browser reach
it at :code:`http://localhost:9000` and nothing else needs to be configured:

.. code::

   AWS_S3_ENDPOINT_URL=http://localhost:9000

If you instead run the stack in Docker, the storage container is not reachable
under the same name from inside the Docker network and from the host. In that
case, give the container a network alias, expose the S3 port on the host, add
the alias to your :code:`/etc/hosts` pointing at :code:`127.0.0.1`, and use that
alias in :code:`AWS_S3_ENDPOINT_URL`, so that the URL resolves both inside and
outside the Docker network.

Configuring CORS
................

Since the browser loads S3 contents from a different origin than the application
server, the storage backend has to send the appropriate CORS headers. Without
them you will see error messages such as "The Same Origin Policy disallows
reading the remote resource at http://localhost:9000/..." and "Reason: CORS
request did not succeed".

SeaweedFS takes the CORS configuration per bucket through the regular S3 API, so
it can be applied with any S3 client:

.. code:: bash

    $ aws --endpoint-url $AWS_S3_ENDPOINT_URL --region us-east-1 \
        s3api put-bucket-cors --bucket $AWS_STORAGE_BUCKET_NAME \
        --cors-configuration file://cors.json

where :code:`cors.json` allows the origin the application is served from, e.g.:

.. code:: json

    {
      "CORSRules": [
        {
          "AllowedOrigins": ["http://localhost:8000"],
          "AllowedMethods": ["GET", "PUT", "POST", "HEAD"],
          "AllowedHeaders": ["*"],
          "ExposeHeaders": ["ETag"]
        }
      ]
    }

In the development stack this is done by :code:`devbox run setup-storage`, which
creates the bucket and applies the CORS policy in one step. Alternatively,
SeaweedFS accepts a global list of allowed origins on startup via the
:code:`-s3.allowedOrigins` command line flag.













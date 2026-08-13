Storage Backend
===============

.. role:: bash(code)
   :language: bash

Topobank stores all user data — the uploaded measurement files, derived data and
analysis results — on a storage backend that is configured through
`django-storages <https://django-storages.readthedocs.io/>`_.

Two backends are supported:

- :code:`django.core.files.storage.FileSystemStorage` stores the files in a local
  directory. This is the default and requires no additional services.
- :code:`storages.backends.s3boto3.S3Boto3Storage` stores the files on an
  S3-compatible object store. This is what production uses, and it is the only
  configuration that supports uploading files directly from the browser to the
  object store, bypassing the application server.

The application selects the backend with the :code:`USE_S3_STORAGE` setting, see
:doc:`deploy` for the full list of related settings. The test settings instead
take the backend from :code:`STORAGE_BACKEND` and derive :code:`USE_S3_STORAGE`
from it, see below.

S3 in development and testing
-----------------------------

Development and continuous integration use
`SeaweedFS <https://github.com/seaweedfs/seaweedfs>`_ as a local, S3-compatible
object store. A single :code:`weed` process provides everything that is needed:

.. code:: bash

    $ mkdir -p .seaweedfs-data
    $ weed server -ip=127.0.0.1 -dir=.seaweedfs-data -filer -s3 -s3.port=9000

The S3 API is then available at :code:`http://localhost:9000`. There is no
dedicated health endpoint; the gateway answers an unauthenticated request with
HTTP 403 as soon as it is listening, which is enough to probe for readiness.

Credentials are configured either with an identity configuration file passed as
:code:`-s3.config`, or — if no such file is given — by setting
:code:`AWS_ACCESS_KEY_ID` and :code:`AWS_SECRET_ACCESS_KEY` in the environment of
the :code:`weed` process, from which SeaweedFS derives a matching admin identity.

SeaweedFS does not create buckets implicitly, so the bucket has to exist before
the application uses it:

.. code:: bash

    $ aws --endpoint-url $AWS_S3_ENDPOINT_URL --region us-east-1 \
        s3 mb s3://$AWS_STORAGE_BUCKET_NAME

The development stack (see :code:`ce-devbox`) wraps this, together with the CORS
configuration described in :doc:`development`, in
:code:`devbox run setup-storage`.

Running the tests against S3
............................

By default the test suite uses :code:`FileSystemStorage`. To exercise the S3 code
paths instead, point :code:`STORAGE_BACKEND` at the S3 backend and configure the
connection:

.. code:: bash

    $ export STORAGE_BACKEND=storages.backends.s3boto3.S3Boto3Storage
    $ export AWS_ACCESS_KEY_ID=admin
    $ export AWS_SECRET_ACCESS_KEY=secret12
    $ export AWS_STORAGE_BUCKET_NAME=topobank-test
    $ export AWS_S3_ENDPOINT_URL=http://localhost:9000
    $ pytest

Continuous integration runs the suite both ways: once with
:code:`FileSystemStorage` and once against a SeaweedFS service.

S3 in production
----------------

Production uses the S3 service of the computing centre rather than a local
object store. Create a user (e.g. "topobank") there, and create an access key for
that user, which gives you an "Access Key ID" and a "Secret Access Key". Keep
both in a password manager and configure them as :code:`AWS_ACCESS_KEY_ID` and
:code:`AWS_SECRET_ACCESS_KEY`; see :doc:`deploy` for the remaining settings.

Inspecting the contents of a bucket
-----------------------------------

Any S3 client can be used to look at the stored data. With the AWS CLI:

.. code:: bash

    $ aws --endpoint-url $AWS_S3_ENDPOINT_URL s3 ls s3://$AWS_STORAGE_BUCKET_NAME --recursive

SeaweedFS additionally serves a filer user interface on
:code:`http://localhost:8888` that shows the stored files as a directory tree.

.. note::

    If the endpoint uses a certificate that does not match its host name — which
    is currently the case for the computing centre's S3 gateway — clients need to
    be told to skip certificate verification (:code:`--no-verify-ssl` for the AWS
    CLI). The corresponding Django setting is :code:`AWS_S3_VERIFY=False`.

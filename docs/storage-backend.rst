Storage Backend
===============

.. role:: bash(code)
   :language: bash

.. todo:: So far the storage backend are files. Planned to changed to S3.


Testing the S3 backend with minio
---------------------------------

Using Minio client in Docker image to test connection.

.. code:: bash

    $ docker run -it --entrypoint=/bin/sh minio/mc

Adding S3 host:

.. code:: bash

    / # mc config host add rz-uni-freiburg https://s3gw1.vm.privat:8082/ <Access Key ID> <Secret Access Key> --insecure

.. warning:: Problem so far: Certificate is not valid: "

.. code:: bash

    / # mc ls rz-uni-freiburg
    mc: <ERROR> Unable to list folder. Get https://s3gw1.vm.privat:8082/: x509: certificate is valid for 12254640, not s3gw1.vm.privat

With --insecure it works:

.. code:: bash

    / # mc ls rz-uni-freiburg --insecure

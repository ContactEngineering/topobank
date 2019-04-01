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

Creating topobank user in RZ's S3
---------------------------------

Create user with name "topobank".


Created "Topobank Group" with unique name "topobank"
and added user "topobank" to this group.

In User "topobank" ("Edit S3 keys"), create ACCESS key with

- "Access Key ID" and
- "Secret Access Key"

Take a note in a password manager or download a CSV with the data.
Then use these values in Topobank's config.


Testing
-------

Install "s3cmd" from your system's package repository.
Currently I cannot get access with it.

It works with minio as described above, but so far only with the original "root" account,
not with the "topobank" account.


Alternative: Install FUSE lib, so you can see the bucket in your file manager, e.g. caja in Ubuntu:

.. code:: bash

  sudo apt-get install s3fs
  echo <ACCESS_KEY>:<SECRET_KEY> > ~/.passwd-s3fs
  chmod 600 ~/.passwd-s3fs
  mkdir ~/mnt/s3-drive
  s3fs <bucketname> ~/s3-drive

See: https://cloud.netapp.com/blog/amazon-s3-as-a-file-system
Still have problems using this option..

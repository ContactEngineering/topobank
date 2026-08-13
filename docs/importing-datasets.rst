Importing datasets into the local environment
=============================================

Make sure that the docker is up and django service is running.

Download the zip file containing the datasets and place in the local topobank subdirectory.

Run the following command from the topobank subdirectory.

.. code:: bash

    docker compose run --rm django python manage.py import_surfaces <username> <surface container file.zip>

You have to replace username with the correct username. In order to find it,
sign in and enter the "User Profile" page of the local instance and take the
last part of the URL.

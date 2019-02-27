Deploy
========

This is where you describe how the project is deployed in production.

.. role:: bash(code)
   :language: bash


Operating System
----------------

This deployment is made on Ubuntu 18.04.01 LTS.

Update the system using

.. code:: bash

    apt-get update
    apt-get upgrade


Install packages
----------------

Ensure you have sudo permissions.

.. code:: bash

    sudo apt-get install python3.7 git nginx

..
    Missing: postgresql and related


Alternative to python3.7 system package
---------------------------------------

Download latest miniconda and create a python 3.7 environment from there.
Should also work on systems which do not have a python3.7 interpreter.

.. code:: bash

    wget https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh
    bash Miniconda3-latest-Linux-x86_64.sh
    conda create -n topobank python=3.7
    conda activate topobank

All further commands and actions on this machine which are done in
a virtual environment have to be done in the conda environment instead.

Generate user
-------------

.. code:: bash

    sudo adduser topobank --disabled-password

This user will be used to run the application. You cannot login by password,
but we'll set it up that you can use SSH keys to transfer code.


Create SSH keys and allow topobank user to access github
--------------------------------------------------------

The current source code is on github. Each release is tagged on the
master branch. We need to access the master branch on github from
the :code:`topobank` user. In order to do so, we need a pair of
SSH keys.

Login as user `topobank` e.g. by

.. code:: bash

   sudo su topobank

Go to home directory and generate SSH keys:

.. code:: bash

   cd
   ssh-keygen -t ecdsa -b 521

Accept the suggested file name, choose no pass phrase.

.. Really no pass phrase?

Allow access to github by uploading the public key :bash:`~/.ssh/id_ecdsa.pub`
on the approriate github page.

Add remote repository by

.. code:: bash

   git remote add origin git@github.com:pastewka/TopoBank.git

Use this repository as source for the source code.

Alternative local repository if github access is not possible
-------------------------------------------------------------

Prepare remote repository and access
....................................

As alternative, if the direct access to Github is not possible:

Login as user `topobank` e.g. by

.. code:: bash

   sudo su topobank

Create a directory for the git repository

.. code:: bash

   cd
   mkdir -p git/topobank.git
   cd git/topobank.git
   git init --bare

Now we need to be able to push the current repository from a development machine
to this repository here.

First, be sure that the :code:`topobank` user has your public SSH key.
You can e.g. copy&paste the entry from file :code:`~/.ssh/authorized_keys` from the user
you are using in order to connect to the production machine to the equivalent file of the user
:code:`topobank`. As user :code:`topobank` do

   cd
   mkdir .ssh
   chmod 700 .ssh
   vim .ssh/authorized_keys
   (here paste the public key of your user who connected to the machine)

Afterwards it should be possbile to connect without password via

   ssh topobank@<server>

For :code:`<server>` use the name of the server.


Push current version of the source code
.......................................

For the following on your development machine it's suggested to add a host entry into
your :bash:`~/.ssh/config` file like

.. code:: bash

    Host topobank-prod
    HostName <server>
    User topobank

Then you can connect via

.. code:: bash

    ssh topobank-prod

as your user or via

.. code:: bash

    ssh topobank@topobank-prod

as :code:`topobank` user.

In order to have source code on the server, now do the following on your development machine,
in the source directory of *TopoBank*:

.. code:: bash

   git remote add topobank-prod topobank@topobank-prod:git/topobank.git

Now it should be possible to push the code:

.. code:: bash

   git push topobank-prod master

(choose whatever branch or code you want to use on the VM)

Login onto the production machine, as user :code:`topobank`:

.. code:: bash

   ssh topobank@topobank-prod

.. code:: bash

   git clone -b 19_dockerize file:///home/topobank/git/topobank.git/




Register analysis functions
---------------------------

When deploying or during development, if you change the definition
of analysis functions (via decorator in `functions.py`), register
the current set of analysis functions in the database.

.. code:: bash
    python manage.py register_analysis_functions


Creating Wheel for PyCo
-----------------------

As long as PyCo is not installable via pip without github account,
we create a wheel package and put it into the Docker container.

































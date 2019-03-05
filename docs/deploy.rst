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

    sudo apt-get install python3.7 git

Make sure you DON'T have the follwing installed, since they come as containers:

- webserver (like nginx, apache)
- postgresql


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

Install Docker
--------------

See docker-installation.rst.

Make sure to use "topobank" instead of "${USER}" during the step

.. code:: bash

  sudo usermod -aG docker ${USER}

Install "docker-compose"
------------------------

On a development machine, you could install docker-compose via pip.
Alternatively and here on production, in order not to need another python environment,
we install the binaries as suggested on the home page:

  https://docs.docker.com/compose/install/

.. code:: bash

   curl -L "https://github.com/docker/compose/releases/download/1.23.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
   chmod +x /usr/local/bin/docker-compose


Copy current PyCo source code to VM
-----------------------------------

If available, use tarball from the release in GitHub.
If not, create your own tarball by entering a working directory
with a PyCo checkout and execute:

.. code:: bash

    git archive --format=tar --prefix=PyCo-0.30.0/ v0.31.0  | gzip > PyCo-0.30.0.tar.gz

Don't forget the '/' at the end of the prefix!
THIS DOES NOT WORK LIKE THIS, PROBLEMS WITH VERSION..

Copy the tarball to the directory where you want to build the containers, here
on the virtual machine:

.. code:: bash

    scp PyCo-0.31.0.tar.gz topobank-vm:topobank/


Configure services
------------------

.. code:: bash

   cd topobank

There are several environment files which are used to configure the services.

After configuring the values it is advised to backup the files through a secure channel
in order to be able to rebuild everything from scratch using backups of the database.
Do not check in the files currently used in production into the repository, because e.g. Django's secrect key
could be used to hack the site.

There is a command

.envs/.production/.caddy
........................

Configures the web server `caddy`. Example:

.. code::

    # Caddy
    # ------------------------------------------------------------------------------
    DOMAIN_NAME=contact.engineering

.envs/.production./django
.........................

Configures Python part: Django, Celery

.. code::

    # General
    # ------------------------------------------------------------------------------
    # DJANGO_READ_DOT_ENV_FILE=True
    DJANGO_SETTINGS_MODULE=config.settings.production
    DJANGO_SECRET_KEY=<put in here your secret key>
    DJANGO_ADMIN_URL=<put here some random string>
    DJANGO_ALLOWED_HOSTS=topobank.contact.engineering

    # Security
    # ------------------------------------------------------------------------------
    # TIP: better off using DNS, however, redirect is OK too
    DJANGO_SECURE_SSL_REDIRECT=False

    # Email
    # ------------------------------------------------------------------------------
    #MAILGUN_API_KEY=
    #DJANGO_SERVER_EMAIL=
    #MAILGUN_DOMAIN=
    # Here we will have an SMTP account from RZ and no longer use postmark/anymail
    POSTMARK_SERVER_TOKEN=<postmark token taken from your postmark account>
    DJANGO_DEFAULT_FROM_EMAIL=<a valid e-mail address to sent from, e.g. roettger@tf.uni-freiburg.de, depends on postmark>

    # django-allauth
    # ------------------------------------------------------------------------------
    DJANGO_ACCOUNT_ALLOW_REGISTRATION=True

    # Gunicorn
    # ------------------------------------------------------------------------------
    WEB_CONCURRENCY=4
    # This is the numer of workers, see also: https://gunicorn-docs.readthedocs.io/en/latest/settings.html

    # Celery
    # ------------------------------------------------------------------------------
    CELERY_BROKER_URL=amqp://guest:guest@rabbitmq:5672//
    CELERY_RESULT_BACKEND=cache+memcached://memcached:11211/

    # Flower
    CELERY_FLOWER_USER=<a long random string>
    CELERY_FLOWER_PASSWORD=<a very long random string>

    # ORCID authentication
    # ------------------------------------------------------------------------------
    ORCID_CLIENT_ID=<from your ORCID configuration>
    ORCID_SECRET=<from your ORCID configuration>

Replace all "<...>" values with long random strings. For the Django secret and the passwords
you can also use punctuation.

Mailgun: Could be used to sent mails, register at https://www.mailgun.com/
Postmark: https://account.postmarkapp.com/sign_up

.envs/.production/.postgres
...........................

Configures the PostGreSQL database:

.. code::

    # PostgreSQL
    # ------------------------------------------------------------------------------
    POSTGRES_HOST=postgres
    POSTGRES_PORT=5432
    POSTGRES_DB=topobank
    POSTGRES_USER=<a long random string suitable for user names>
    POSTGRES_PASSWORD=<a very long random string>

These settings are recognized by the "postgres" service and then used to automatically create a user+database.

Build images for all services
-----------------------------

.. code:: bash

   cd topobank
   docker-compose -f production.yml build


Test sending mails
------------------

With a running django container do:

$ docker-compose -f production.yml run --rm django python manage.py shell
>>> from django.core.mail import send_mail
>>> send_mail('test','','topobank@contact.engineering',['roettger@tf.uni-freiburg.de'])

Use your own mail address here!

Or instead in one command:

$ docker-compose -f production.yml run --rm django python manage.py shell -c "from django.core.mail import send_mail;send_mail('test','','topobank@contact.engineering',['roettm@exlex.org'])"



Known problems
--------------

PostGreSQL user does not exist
..............................

Example:

.. code::

   FATAL:  password authentication failed for user "dsdjfjer84jf894jd9f"
   DETAIL:  Role "dsdjfjer84jf894jd9f" does not exist.


Probably the image has already a user created. If there is no valuable data yet, delete the image and build again.

.. code:: bash

  docker container rm topobank_postgres_1
  docker system prune
  docker volume rm $(docker volume ls -qf dangling=true)
  docker-compose -f production.yml build


Further preparation of first run
--------------------------------

.. code:: bash

    docker-compose -f production.yml run --rm django python manage.py migrate
    docker-compose -f production.yml run --rm django python manage.py register_analysis_functions
    docker-compose -f production.yml run --rm django envsubst < orcid.yaml.template > orcid.yaml
    docker-compose -f production.yml run --rm django python manage.py loaddata orcid.yaml

TODO Check if these commands are here at the right place.

Register analysis functions
---------------------------

When deploying or during development, if you change the definition
of analysis functions (via decorator in `functions.py`), register
the current set of analysis functions in the database.

.. code:: bash
    python manage.py register_analysis_functions


































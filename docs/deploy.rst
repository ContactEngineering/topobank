Deploy
========

This is where you describe how the project is deployed in production.

.. role:: bash(code)
   :language: bash


Connection to virtual machine and checking fingerprints
-------------------------------------------------------

Connect to virtual machine by using SSH. I suggest to use an entry like
::

    Host topobank-prod
    HostName topobank.vm.uni.freiburg.de
    User <your user name>

in your SSH config (Linux: `~/.ssh/config`).
During first connect you will be asked whether the host fingerprint is ok.
In order to check this, you need the correct fingerprints of the machine.

The fingerprints can be found out by anyone who can already login savely by using

.. code:: bash

    for i in /etc/ssh/ssh*.pub; do ssh-keygen -l -f $i; done

or in MD5 format:

.. code:: bash

    for i in /etc/ssh/ssh*.pub; do ssh-keygen -E md5 -l -f $i; done

Currently the output for host `topobank.vm.uni-freiburg.de` is::

    $ for i in /etc/ssh/ssh*.pub; do ssh-keygen -l -f $i; done
    1024 SHA256:yRL1VvLBpwxz8wLxkXxigjiA2ni4lCwSTpE+4omyydg root@topobank (DSA)
    256 SHA256:a4pMoQ1LaZ9QCrbINIFAvDI41MDcj4If9V5e0UNLKsA root@topobank (ECDSA)
    256 SHA256:qb2MXg/qU3vGmk/X5NP/TgnNuj89qkWN5QpQFEuHC0s root@topobank (ED25519)
    2048 SHA256:ADHy+xaUcJeWcQsxoYSh7St8qh90eF2tgq+PSI0s3zo root@topobank (RSA)

    $ for i in /etc/ssh/ssh*.pub; do ssh-keygen -E md5 -l -f $i; done
    1024 MD5:41:1c:15:7a:fa:9b:f4:ce:e1:b8:ac:17:6f:cc:5d:8e root@topobank (DSA)
    256 MD5:d4:fb:8e:df:3b:66:3a:ba:b1:c9:98:b6:50:16:f1:e9 root@topobank (ECDSA)
    256 MD5:83:59:09:9b:e8:ee:94:5d:31:1d:e3:c6:50:24:f3:28 root@topobank (ED25519)
    2048 MD5:d9:8b:fb:69:dc:1b:04:e6:8a:77:d6:7f:32:35:c2:bf root@topobank (RSA)

If the fingerprints are okay, you can be sure to connect to the machine without someone in between.

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

    sudo apt-get install git

Make sure you DON'T have the follwing installed, since they run as docker-compose services in containers:

- webserver (like nginx, apache)
- postgresql

Installation of docker will be done later manually.

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

.. code::bash

   cd
   mkdir .ssh
   chmod 700 .ssh
   vim .ssh/authorized_keys
   (here paste the public key of your user who connected to the machine)

Afterwards it should be possbile to connect without password via

.. code:: bash

   ssh topobank@<server>

For :code:`<server>` use the name of the server, e.g. `topobank.vm.uni-freiburg.de`.


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

Clone the repository and create a working directory which will be used in order to create Docker containers later:

.. code:: bash

   git clone -b master file:///home/topobank/git/topobank.git/

Currently during testing I'm using the branch `19_dockerize`, so I'm doing

.. code:: bash

   git clone -b 19_dockerize file:///home/topobank/git/topobank.git/

instead.

Install Docker
--------------

See :ref:`docker-install-ubuntu`. Make sure to use "topobank" instead of "${USER}" during the step

.. code:: bash

  sudo usermod -aG docker ${USER}

Current version used:

.. code:: bash

    $ docker version
    Client:
     Version:           18.09.3
     API version:       1.39
     Go version:        go1.10.8
     Git commit:        774a1f4
     Built:             Thu Feb 28 06:53:11 2019
     OS/Arch:           linux/amd64
     Experimental:      false

    Server: Docker Engine - Community
     Engine:
      Version:          18.09.3
      API version:      1.39 (minimum version 1.12)
      Go version:       go1.10.8
      Git commit:       774a1f4
      Built:            Thu Feb 28 05:59:55 2019
      OS/Arch:          linux/amd64
      Experimental:     false


Install "docker-compose"
------------------------

On a development machine, you could install docker-compose via pip.
Maybe this also works in production, but used now another way:

Alternatively and here on production, in order not to need another python environment,
we install the binaries as suggested on the home page:

  https://docs.docker.com/compose/install/

.. code:: bash

   curl -L "https://github.com/docker/compose/releases/download/1.23.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
   chmod +x /usr/local/bin/docker-compose

Current version used:

.. code:: bash

    $ docker-compose --version
    docker-compose version 1.23.2, build 1110ad01

Copy current PyCo source code to VM
-----------------------------------

If available, use tarball from the release in GitHub.

Copy the tarball to the directory where you want to build the containers, here
on the virtual machine:

.. code:: bash

    scp PyCo-0.31.0.tar.gz topobank-vm:topobank/

The tarball will be automatically extracted and used through a Dockerfile.

If a don't have a tarball, create your own tarball by entering a working directory
with a PyCo checkout and execute:

.. code:: bash

    git archive --format=tar --prefix=PyCo-0.30.0/ v0.31.0  | gzip > PyCo-0.30.0.tar.gz

Don't forget the '/' at the end of the prefix!

.. todo:: THIS DOES NOT WORK LIKE THIS YET, problems if the version does not match the branch version.

Change working directory
------------------------

All further actions will take place in a subdirectory.

.. code:: bash

   cd topobank

Configure services
------------------

There are several environment files which are used to configure the services. They are all placed
under `.envs`:

- `.envs/.local`: configuration files for development
- `.envs/.production`: configuration files for production

After configuring the values it is advised to backup the files through a secure channel
in order to be able to rebuild everything from scratch using backups of the database.
Do not check in the files currently used in production into the repository, because e.g. Django's secrect key
could be used to hack the site.

.. todo:: Add information where to place this information.

Config file `.envs/.production/.caddy`
......................................

Configures the web server `caddy`. Example:

.. code::

    # Caddy
    # ------------------------------------------------------------------------------
    DOMAIN_NAME=contact.engineering

Caddy is used because it allows for having an SSL-secured site very easily.

Config file `.envs/.production./django`
.......................................

Configures Python part: Django and Celery. You can use this as template:

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
    # a valid mail address to send from
    DJANGO_DEFAULT_FROM_EMAIL=topobank@imtek.uni-freiburg.de
    DJANGO_EMAIL_URL=smtp+ssl://topobank@imtek.uni-freiburg.de:<REPLACE WITH PASSWORD>@mail.uni-freiburg.de:465

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

Replace all "<...>" values with long random strings or known passwords, as described.
For the Django secret and the passwords you can also use punctuation.


Config file `.envs/.production/.postgres`
.........................................

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

.. _first-run:

Further preparation of first run
--------------------------------

Make sure, ORCID allows topobank to use it for authentication, see:

Update database schema:

.. code:: bash

    docker-compose -f production.yml run --rm django python manage.py migrate

Create entries in database for all analysis functions defined in the code:

.. code:: bash

    docker-compose -f production.yml run --rm django python manage.py register_analysis_functions

Create YAML file with database entry for the social account provider "ORCID".
Then import the data and create the database entry. This is needed to enable the ORCID authentication.
During the creation of `orcid.yaml` the access key and secret needed for ORCID are inserted
from environment variables:

.. code:: bash

    docker-compose -f production.yml run --rm django envsubst < orcid.yaml.template > orcid.yaml
    docker-compose -f production.yml run --rm django python manage.py loaddata orcid.yaml



Get to know docker-compose
--------------------------

This is your interface to interact with all running containers.
Have a look at the possible commands:

.. code:: bash

   cd topobank
   docker-compose -f production.yml -h

In the following sections, we list here some important commands.
You have to be in the subdirectory where the docker-compose file (here `production.yaml`) is.

Build images for all services
.............................

.. code:: bash

   docker-compose -f production.yml build

Creating containers for all services and start
..............................................

.. code:: bash

   docker-compose -f production.yml up -d

The switch `-d` detaches the containers from the terminal, so you can safely log out.

.. DANGER::

    Be careful with the `down` command!! It will remove the containers and all data!!

Viewing logs
............

.. code:: bash

   docker-compose -f production.yml logs

See help with `-h` in order to see more options, e.g. filter for messages of one service.
Example: See only messages of "django" service:

.. code:: bash

   docker-compose -f production.yml logs django

Seeing running processes
........................

See if all services are up and running, their container names, the port redirections:

.. code:: bash

   docker-compose -f production.yml ps

See all processes, ordered by container:

.. code:: bash

   docker-compose -f production.yml top

Start and stop containers
.........................

Do this on all containers:

.. code:: bash

   docker-compose -f production.yml start
   docker-compose -f production.yml stop
   docker-compose -f production.yml restart

Or on individual services:

.. code:: bash

   docker-compose -f production.yml start django
   docker-compose -f production.yml stop django
   docker-compose -f production.yml restart django

Other
.....

Interesting, but not tested is probably the scaling of containers, e.g. the celery workers:

.. code:: bash

   docker-compose -f production.yml scale celeryworker=4





Test sending mails
------------------

With a running django container do:

.. code::bash

    $ docker-compose -f production.yml run --rm django python manage.py shell
    >>> from django.core.mail import send_mail
    >>> send_mail('test subject','test body','topobank@imtek.uni-freiburg.de',['roettger@tf.uni-freiburg.de'])

Use your own mail address here!

Or instead in one command:

.. code:: bash

    $ docker-compose -f production.yml run --rm django python manage.py shell -c "from django.core.mail import send_mail;send_mail('test','','topobank@imtek.uni-freiburg.de',['roettger@tf.uni-freiburg.de'])"

.. todo:: currently this results in "[Errno 99] Cannot assign requested address"


Configuring backup
------------------

.. todo:: document how to do backup and restore

Updating the application
------------------------

.. todo:: document how to do an update if the code changes such that database is kept

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



























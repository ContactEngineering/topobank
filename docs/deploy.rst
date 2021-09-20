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

    sudo apt-get install git supervisor

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

   git remote add origin git@github.com:ComputationalMechanics/TopoBank.git

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
    DJANGO_ALLOWED_HOSTS=contact.engineering

    # Generating topography thumbnails with Firefox
    # ------------------------------------------------------------------------------
    # firefox binary, not the script!
    FIREFOX_BINARY_PATH=/opt/conda/bin/FirefoxApp/firefox
    GECKODRIVER_PATH=/opt/conda/bin/geckodriver

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

    # Storage settings
    # ------------------------------------------------------------------------------
    USE_S3_STORAGE=yes

    AWS_ACCESS_KEY_ID=<insert your access key id>
    AWS_SECRET_ACCESS_KEY=<insert your secret acccess key>

    # the bucket will be created if not available, you can use different buckets for development and production:
    AWS_STORAGE_BUCKET_NAME=topobank-assets-production
    # replace with your endpoint url, you can use localhost:8082 if you want to use an SSH tunnel to your endpoint:
    AWS_S3_ENDPOINT_URL=<insert your endpoint url>
    AWS_S3_USE_SSL=True # this is default
    AWS_S3_VERIFY=False  # currently the certificate is not valid

    # Backup Settings
    # ------------------------------------------------------------------------------
    #
    # Periodically database dumps will be written to the defined S3 bucket
    # with prefix "backup".
    #
    # For more information about the used docker image: https://hub.docker.com/r/codestation/go-s3-backup/
    #
    # set 6 (!) cron job-like fields: secs minutes hours day_of_month month day_of_week
    # or predefined schedules
    # or "none" for single backup once
    # for more information see: https://godoc.org/github.com/robfig/cron
    DBBACKUP_SCHEDULE=@daily


Replace all "<...>" values with long random strings or known passwords, as described.
For the Django secret and the passwords you can also use punctuation.

Or better, use the file `.envs/.production/.django.template` as start.

If `USE_S3_STORAGE` is `no`, a local directory will be used for file storage.


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

Then import terms and conditions:

.. code:: bash

    docker-compose -f production.yml run --rm django python manage.py import_terms site-terms 1.0 topobank/static/other/TermsConditions.md

After these conditions are installed, they are active (default activation time is installation time) and
the user is asked when signing in. The terms and conditions (with slug "site-terms") must be accepted in order to
use the application.

.. _automated-restart:

Configuration of automated restart
----------------------------------

First, once make sure, the supervisor service uses the user "topobank"
for the socket. Then the user "topobank" can start and stop the application
without sudo. Therefore add the line

.. code::

    chown=topobank

to the section :code:`[unix_http_server]` of the file :code:`/etc/supervisor/supervisord.conf`.
Afterwards the file may look like this::

    ; supervisor config file

    [unix_http_server]
    file=/var/run/supervisor.sock   ; (the path to the socket file)
    chmod=0700                       ; sockef file mode (default 0700)
    chown=topobank

    [supervisord]
    logfile=/var/log/supervisor/supervisord.log ; (main log file;default $CWD/supervisord.log)
    pidfile=/var/run/supervisord.pid ; (supervisord pidfile;default supervisord.pid)
    childlogdir=/var/log/supervisor            ; ('AUTO' child log dir, default $TEMP)

    ; the below section must remain in the config file for RPC
    ; (supervisorctl/web interface) to work, additional interfaces may be
    ; added by defining them in separate rpcinterface: sections
    [rpcinterface:supervisor]
    supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

    [supervisorctl]
    serverurl=unix:///var/run/supervisor.sock ; use a unix:// URL  for a unix socket

    ; The [include] section can just contain the "files" setting.  This
    ; setting can list multiple files (separated by whitespace or
    ; newlines).  It can also contain wildcards.  The filenames are
    ; interpreted as relative to this file.  Included files *cannot*
    ; include files themselves.

    [include]
    files = /etc/supervisor/conf.d/*.conf


Then add a configuration for the topobank program.
Follow the instructions here:

  https://cookiecutter-django.readthedocs.io/en/latest/deployment-with-docker.html?highlight=restart#example-supervisor

That is, as root copy this contents to `vim /etc/supervisor/conf.d/topobank.conf`:

.. code::

    [program:topobank]
    user=topobank
    command=docker-compose -f production.yml up
    directory=/home/topobank/topobank
    redirect_stderr=true
    autostart=true
    autorestart=true
    priority=10


(including `user` option!)

Make sure, topobank completely stopped.

.. TODO Here some documentation about calling some management commands are missing. See "Updating the application"!

Reread the supervisor configuration and start:

.. code:: bash

    supervisorctl reread
    supervisorctl start topobank

Status check:

.. code:: bash

    supervisorctl status

Make sure you are user "topobank" in the directory `/home/topobank/topobank`.
All docker containers should be running:

.. code:: bash

    topobank@topobank:~/topobank$ docker-compose -f production.yml ps
             Name                        Command               State                         Ports
    ---------------------------------------------------------------------------------------------------------------------
    topobank_caddy_1          /bin/parent caddy --conf / ...   Up      2015/tcp, 0.0.0.0:443->443/tcp, 0.0.0.0:80->80/tcp
    topobank_celerybeat_1     /entrypoint /start-celerybeat    Up
    topobank_celeryworker_1   /entrypoint /start-celeryw ...   Up
    topobank_dbbackup_1       /entrypoint                      Up
    topobank_django_1         /entrypoint /start               Up
    topobank_flower_1         /entrypoint /start-flower        Up      0.0.0.0:5555->5555/tcp
    topobank_memcached_1      docker-entrypoint.sh memcached   Up      11211/tcp
    topobank_postgres_1       docker-entrypoint.sh postgres    Up      5432/tcp
    topobank_rabbitmq_1       docker-entrypoint.sh rabbi ...   Up      25672/tcp, 4369/tcp, 5671/tcp, 5672/tcp


Logging output can be seen with this command:

.. code:: bash

    docker-compose -f production.yml logs -f


Get to know docker-compose
--------------------------

This is your interface to interact with all running containers.
Login as user :code:`topobank` and have a look at the possible commands:

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

A similar command (without `-d`) is called on start of the host, if `supervisor` has been configured
as described here: :ref:`automated-restart`.

.. DANGER::

    Be careful with the :code:`down` command!! It will remove the containers and all data!!

Viewing logs
............

.. code:: bash

   docker-compose -f production.yml logs

See help with `-h` in order to see more options, e.g. filter for messages of one service.
Use `-f` in order to follow logs.

Example: See only messages of "django" service and follow them:

.. code:: bash

   docker-compose -f production.yml logs -f django

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

We want to backup the Django database in order to be able to restore
it in case of failures. In order to do so we regularly create dumps of the database
and push them to the same S3 bucket as the media files (with another prefix).


Automated backups using a predefined service
--------------------------------------------

In the docker compose files there is a predefined service named "dbbackup". This service is based on a
docker image named "codestation/postgres-s3-backup", which stores postgres dumps to an S3 backend
using a scheduler.

The docker-compose configuration for local development also starts a local "minio" S3 service
to store the media files and stores the dumps. It is used automatically.

The docker-compose configuration for production also uses the configured S3 connection, but there
is no local minio service installed.

The backup is always saved with a prefix "backup", so your dump files e.g. look like this:

.. code::

    backup/postgres-backup-20190410213318.sql
    backup/postgres-backup-20190410213319.sql
    [...]

The numbers in the file name is the timestamp of the backup.

As additional settings for the backup, you define the schedule in the config file `.envs/.local/.django`
or `.envs/.production/.django` e.g.:

.. code::

   DBBACKUP_SCHEDULE=@daily

for daily backups. Also crontab-like entries are allowed. For more information about how to define the schedule,
see  https://godoc.org/github.com/robfig/cron.

Then, after starting the containers, the backup is done automatically.

In order to backup once without schedule in production, run

.. code:: bash

    docker-compose -f production.yml run --rm -e DBBACKUP_SCHEDULE=none dbbackup


Restoring database from a backup
--------------------------------

The general idea is

- stop the application
- copy a dump file from the S3 bucket to a local directory
- drop the current database
- use posgresql commands to restore the database from the dump

This process is partly automated. Two ways to accomplish this are discussed.

Using built-in dbbackup container to restore
............................................

This is the container which is also used to create the backups periodically.
First stop the application:

.. code:: bash

    docker-compose -f production.yml stop

Start only the postgresql part:

.. code:: bash

    docker-compose -f local.yml up postgres dbbackup

Open another terminal.

Restore the database by dropping the old database and importing the latest dump from S3:

.. code:: bash

    docker-compose -f local.yml run --rm -e RESTORE_DATABASE=1 dbbackup

Setting the variable `RESTORE_DATABASE=1` restores the database immediately instead of starting the scheduler
again. See `compose/production/dbbackup/entrypoint` for details.

Then stop the two services in the first terminal. Afterwards restart all the stack:

.. code:: bash

    docker-compose -f production.yml up -d

The application should work with the restored database.
Be aware that there could be inconsistencies:

- there could be topography entries in the database which point to a topography file
  which does not exist (could lead to an error in the application)
- there could be topography files left on the S3 storage for which no topography exists any more

Using built-in restore command from django-cookiecutter
.......................................................

NOT TESTED. Another idea is to manually copy backup one file to
the volume `production_postgres_data_backups` and to use the restore
command as described on

 https://cookiecutter-django.readthedocs.io/en/latest/docker-postgres-backups.html

Not sure yet whether the dump format is correct.

Alternative backup strategy (more manual work)
..............................................

(INCOMPLETE)

For creating the database dumps, we could alternatively use the built-in functionality of `cookiecutter-django`, as
you can read here:

  https://cookiecutter-django.readthedocs.io/en/latest/docker-postgres-backups.html

In short: Backups can be manually triggered by
.. code:: bash

    $ docker-compose -f production.yml exec postgres backup

This will create a dump file in the volume `production_postgres_data_backups` on the host,
so they are persistent if you recreate the Docker containers.
With this command you can list the backups in the volume:
.. code:: bash

    docker-compose -f production.yml exec postgres backups

Note the trailing "s" in "backups".

If you have a backup file name, e.g. `backup_2018_03_13T09_05_07.sql.gz`, you can restore the
database with (PLEASE STOP APPLICATION FIRST - "stop", not "down"):

.. code:: bash

    $ docker-compose -f local.yml exec postgres restore backup_2018_03_13T09_05_07.sql.gz

We don't want to rely on the virtual machine only. In order to save the dump on another system,
we dump the files into the S3 bucket used for the topography files.

The topography files, or all media files in general, are saved in a bucket with the prefix `media/`.
The backups should be saved with the prefix `backup/`.
Here we use a command line tool for copying the dumpy into the bucket: `s3mcd`.

Install the tool on Ubuntu by

.. code:: bash

   $ sudo apt-get install s3cmd

Create a config file `~/.s3cfg` on the host in the home directory of the `topobank` user:

.. code::

    access_key=<your access key>
    secret_key=<your secret key>
    host_base=<your S3 host>:<your port>
    host_bucket=<your S3 host>:<your port>/%(bucket)

Change these values appropriately. See the man page of `s3cmd` for more options (under OPTIONS).

This code can be used to find out the physical directory of the host volume with the backups

.. code:: bash

    docker volume inspect topobank_production_postgres_data_backups -f '{{ .Mountpoint  }}'

You could use this in order to manually create a cron job which periodically
syncs the contents of the volume `production_postgres_data_backups` to S3.
When using cron for this, also make sure to delete dumps which are too old, but always keep
a maximum number of dumps.

In case of restore, you could first just use the locally available dumps as described on

    https://cookiecutter-django.readthedocs.io/en/latest/docker-postgres-backups.html

If you need the dumps from S3, e.g. the dumps are locally lost, you could use `s3cmd` to sync
the other way round.

More ideas:

- https://github.com/chrisbrownie/docker-s3-cron-backup







Updating the application
------------------------

Login to the VM as user topobank and change to the working directory:

.. code:: bash

    cd ~/topobank

Stop the application
....................

If you are using `supervisor`, do

.. code:: bash

   supervisorctl stop topobank

If you don't use `supervisor`, just call

.. code:: bash

    docker-compose -f production.yml stop

(this won't help when started via supervisor, because topobank is immediately restarted again).

For 0.15.x -> 0.16.0: Rewind a migration
........................................

If you upgrade from version 0.15.x to 0.16.0, then a special step ins needed before the code is updated.
For 0.16.0 we switch back from our own fork for "django-termsandconditions" to the official one.

Create a backup copy of the tables `termsandconditions_termsandconditions`
and `user_termsandconditions_termsandconditions`, e.g. by copying as extra tables with a `_sav` suffix in the name.

Then, delete all optional terms in the database, they are no longer supported. Also all references if
they have been accepted by users. Then, before migration, make sure to migrate this app back to an earlier state:

.. code:: bash

  docker-compose -f production.yml run --rm django python manage.py migrate termsandconditions 0003_auto_20170627_1217

If a default for the info is needed, choose an empty string.

Check if the data is complete using the table copies or use them to fix problems.
Delete the backup copies.

Now the missing migrations of django-termsandconditions should apply when doing the migration below.

Update the code
...............

Be sure that the new code is available on the remote repository. Fetch the changes
and apply them to the working directory.

.. code:: bash

    git pull

Refine configuration
....................

Is a change in config files neccessary, e.g. below `.envs/production`?
Are there any new settings?

Adjust the configuration before rebuilding the containers.

Rebuild the containers
......................

.. code:: bash

    docker-compose -f production.yml build

The database should be kept, because it is saved on a Docker "volume" on the host.
You can see the volumes using

.. code:: bash

    docker volume ls

Update configuration/database
.............................

If building the containers was successful, aks yourself these questions:

- Is a migration of the database needed? If yes,
  first create a backup of the database:

  .. code:: bash

    docker-compose -f production.yml run --rm -e DBBACKUP_SCHEDULE=none dbbackup

  Then migrate:

  .. code:: bash

     docker-compose -f production.yml run --rm django python manage.py migrate

  See here for reference: https://cookiecutter-django.readthedocs.io/en/latest/deployment-with-docker.html?highlight=migrate


- Are there new analysis functions? IF yes, do

  .. code:: bash

     docker-compose -f production.yml run --rm django python manage.py register_analysis_functions

  If analysis functions have been replaced or removed, also use switch `--cleanup` or `-c`:

  .. code:: bash

     docker-compose -f production.yml run --rm django python manage.py register_analysis_functions --cleanup

  This will delete all analysis functions no longer referenced by implementations.
  It will also delete all related analysis, so handle with care!

- Is there any need to change sth. in the S3 storage?

  Prepare the S3 storage as needed.

- Is there a change to the file format strings?

  Since version 0.7.4, for each topography the file format specifier is also saved in the
  database in order to do format detection only once on file upload.
  If a file had no format saved before (e.g. for all topographies uploaded before 0.7.4)
  or the file format specifiers change for some reason (e.g. of a major change in PyCo),
  the file format specifiers in the database have to be rewritten.
  This can be done by the management command `set_datafile_format`.
  With this command you get a help string:

  .. code:: bash

     docker-compose -f production.yml run --rm django python manage.py set_datafile_format --help

  Choose whether you want to replace the file format for all topographies (i.e. re-run autodetection)
  or only for those which have no file format saved yet and run again without `--help`.
  You can also do a "dry-run" before, in order to see whether autodetection for any topography will fail.

- Have some new arguments been added to an analysis function?

  You can update all function arguments for all analysis by completing them
  with new keyword arguments which have been added to the code. For this run

  .. code:: bash

     docker-compose -f production.yml run --rm django python manage.py save_default_function_kwargs --dry-run

  first, check whether the result (counts) is you expected and run without `--dry-run`.

- Did you have a default group for the users before? This is introduced in version 0.9.0, so
  when upgrading to this version, you need to call

   .. code:: bash

     docker-compose -f production.yml run --rm django python manage.py ensure_default_group

  once for your database.

  Afterwards all exisiting users will be member of the default group (currently: 'all').
  This is needed for publishing.

- Are there any new permissions introduced for surfaces? You should fix the permissions
  for existing surfaces with

  .. code:: bash

     docker-compose -f production.yml run --rm django python manage.py fix_permissions --dry-run

  once for your database. Check the results: Will those permissions be set which you expect?
  If it's okay, run again without the option `--dry-run`.

  Afterwards all existing users will have all permissions for the surfaces they created
  unless they are already published. When already published, it is assured the correct
  rights have been applied. This is needed for publishing.

- If any analyses have to rerun, e.g. because the format of the analyses result have changed,
  call

  .. code:: bash

     docker-compose -f production.yml run --rm django python manage.py trigger_analyses -h

  with appropriate arguments. As example, if all calculations for analysis functions with
  ids 1, 2, and 3 have to be rerun, call:

  .. code:: bash

     docker-compose -f production.yml run --rm django python manage.py trigger_analyses f1 f2 f3

  This may take some time.

- Is there a change of the internal representation of the "squeezed" data format?

  Currently all data files are saved in an alternative format, the "squeezed datafile".
  Currently this is a NetCDF3 format provided by the package `SurfaceTopography`.
  If this format changes or all squeezed files should be recreated, you should run

  .. code:: bash

     docker-compose -f production.yml run --rm django python manage.py renew_squeezed

  This may take some time. You could use the switch `-b` to do it in the task queue,
  but then you don't know at the end whether it was successful.

- Should the height_scale_factor of all measurements be corrected?

  With version of SurfaceTopography 0.94.0 the reader channels have the information
  whether the height scale factor is fixed by the file contents.
  Before there were some inconsistencies between file contents and the database
  flags for some measurements.

  In order to fix all flags `height_scale_editable` and also `height_scale`, if not editable,
  in the database run first

  .. code:: bash

     docker-compose -f production.yml run --rm django python manage.py fix_height_scale --dry-run

  and look whether the statistics in the output makes sense. If yes, run the command without `--dry-run`
  and the database will be changed accordingly.

- Should the sizes of all measurements be corrected?

  With version of SurfaceTopography 0.94.0 the reader channels have the information
  whether the size is fixed by the file contents.
  Before there were some inconsistencies between file contents and the database
  flags for some measurements.

  In order to fix all flags `size_editable` and also the sizes itself, if not editable,
  in the database run first

  .. code:: bash

     docker-compose -f production.yml run --rm django python manage.py fix_sizes --dry-run

  and look whether the statistics in the output makes sense. If yes, run the command without `--dry-run`
  and the database will be changed accordingly.



Restart application
...................

If everything is okay, start the new containers in the background.

If you are using supervisor, do

.. code:: bash

    supervisorctl start topobank

Without supervisor, call:

.. code:: bash

    docker-compose -f production.yml up -d

Test whether the new application works. See also above link if you want to scale the application,
e.g. having more processes handling the web requests or celery workers.



Generating thumbails
....................

If you need to recompute the topography thumbnails, e.g. if you haven't done this before
or if the code for the thumbnails have changed, you can do this after starting the application stack.
Use the following management command:

.. code:: bash

     docker-compose -f production.yml run --rm django python manage.py create_thumbnails

Note that in order to generate thumbnails, the following environment variables must be set correctly:

.. list-table::
    :widths: 25 75
    :header-rows: 1

    * - Environment Variable
      - Comment
    * - `FIREFOX_BINARY_PATH`
      - absolute path to the firefox **binary**, not the script which is mostly first in `PATH`
    * - `GECKODRIVER_PATH`
      - absolute path to the geckodriver binary



Look into the database
----------------------

You can indirectly connect from outside to the PostGreSQL database, e.g.
by using a tool "PGAdmin". Therefore you an use an SSH tunnel and connect to
the docker container which runs the PostGreSQL database.

First be sure to know the IP address of the docker container running the PostGreSQL database.
Log in to the VM once and execute

.. code:: bash

    docker inspect -f "{{ .NetworkSettings.Networks.topobank_default.IPAddress }}" topobank_postgres_1

Then take a note of the IP. Use this IP in an SSH tunnel, e.g.:

.. code:: bash

    ssh -L 5434:172.19.0.3:5432 topobank-vm

Then on your laptop, use PGAdmin and open a connection to `localhost:5434`.
Use the already open terminal to access the file `.envs/.production/.postgres` in order
to copy & paste the username and password (two long random strings) to PGAdmin.
Afterwards you should be able to open the connection.

.. todo:: There is another way by exposing the postgresql port to the host, but only localhost. Then the IP is not needed.

Purge a user and all his data
-----------------------------

If needed, you can delete a user and all his/her data. This can be useful e.g. in development. Use with care!!
In order to delete the user with username `michael` (check this in database)
and to delete all his surfaces+topographies, use:

.. code:: bash

   docker-compose -f production.yml run --rm django python manage.py purge_user michael

So far, there is no extra question, so this immediately done!

Assign permissions to an existing user
--------------------------------------

If you need for any reason to assign permissions for existing surfaces,
you can open a Django shell with

.. code:: bash

   docker-compose -f production.yml run --rm django python manage.py shell

and enter the following code:

.. code:: python

   from topobank.manager.models import Surface
   from guardian.shortcuts import assign_perm

   for surface in Surface.objects.all():
      for perm in ['view_surface', 'change_surface', 'delete_surface', 'share_surface']:
          assign_perm(perm, surface.user, surface)



Known problems
--------------

Here are some known problems and how to handle them.

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






























.. role:: bash(code)
   :language: bash

Installation on development machine
===================================

.. todo:: So far this section only contains some notes and is far from complete.

This is where you write how to get a new laptop to run this project.

Database User
-------------

Create database user:

.. code:: bash

    sudo bash
    su postgres
    createuser topobank

Alternatively, open a psql console and enter::

    ALTER USER topobank CREATEDB;
    ALTER USER topobank PASSWORD 'topobank';


German description of initialzation of a development machine (to be translated + tested)
----------------------------------------------------------------------------------------

Im "develop"-Branch des "Topobank"-Projekts

 https://github.com/pastewka/TopoBank/tree/develop

gibt es jetzt einen Start-Code mit dem man Topographien hochladen und sich dann eine Liste mit Thumbnails anschauen kann. Die Topographien kann man dann auch (eingeschränkt) ändern und wieder löschen.

Wenn Du Zeit hast, kannst Du vielleicht kannst Du mal probieren, ob Du den Code in einer eigenen Python-Umgebung zum Laufen bekommst und damit etwas probieren. Im Folgenden ist beschrieben, wie es gehen sollte:

Die virtuelle Umgebung und den Code bekommst Du z.B. so

.. code:: bash

    $ git clone -b develop git@github.com:pastewka/TopoBank.git topobank
    $ cd topobank
    $ python3 -m venv venv
    $ . ./venv/bin/activate

Dann Abhängigkeiten installieren:

.. code:: bash

    $ pip install -r requirements/local.txt
    $ pip install matplotlib          # fehlt noch in requirements

(Bei mir unter Ubuntu war hier noch "sudo apt-get install python3-tk" nötig)

PyCo installieren in virtual environment, z.B.

.. code:: bash

     # cd ../PyCo; pip install -r requirements.txt; pip install .
     # ... oder wo auch immer Pyco bei Dir ist

Datenbank (momentan noch SQLite) initialisieren mit

.. code:: bash

     $ python manage.py migrate

Starten der Anwendung mit

.. code:: bash

    $ python manage.py runserver

Dann das passende "mailhog" binary hier

    https://github.com/mailhog/MailHog/releases/v1.0.0

runterladen, irgendwo ablegen und starten. Das fungiert dann als Pseudo-Mailserver und man kann damit im Browser unter

    http://localhost:8025

die Registrierungsmail sehen und den Bestätigungslink anklicken.

Dann solltest Du Dich unter

    http://localhost:8000

registrieren ("Sign Up") und einloggen ("Sign In") können. Der Login-Vorgang kann später geändert werden, ich habe da erstmal den Default genommen.

Bevor Du unter "My Topographies" -> "New" eine Topographie anlegst, bitte noch händisch das Unterverzeichnis "user_1" unter "media/topographies" anlegen, das habe ich im Code vergessen:

.. code:: bash

    $ mkdir topobank/media/topographies/user_1

Hier werden die Dateien vom User mit der ID 1 abgelegt.
(TODO Noch nötig??)

Register existing analysis functions to the database
----------------------------------------------------

On command line, in the correct environment, call

.. code:: bash

    $ python manage.py register_analysis_functions

All available analysis functions will be added to the database if
not already happend. Currently errors during the database operations are not catched.

Creating a superuser
--------------------

Is this needed?

In order to activate the ORCID authentication we need to have a super user who enters ...


Create ORCID configuration directly in database
-----------------------------------------------

::

     INSERT INTO socialaccount_socialapp (provider,name,client_id,key,secret)
            VALUES ('orcid', 'ORCID', '<insert client id here>', '','<insert password here>')

Setup of RabbitMQ on local machine
----------------------------------

If you don't use docker-compose to start all services, you may want to install "rabbitmq" on
your local computer. Here an example for Ubuntu:

.. code:: bash

    sudo rabbitmqctl add_user roettger secert7$
    sudo rabbitmqctl add_vhost topobank
    sudo rabbitmqctl set_permissions -p topobank roettger ".*" ".*" ".*"

In production choose another user name, e.g. "django" or topobank

.. todo:: Probably running in a docker container is much easier, to be tested.




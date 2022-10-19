
Managing the application on Docker Swarm
========================================

Activating a node
-----------------

Given a node which has availability "Drain", it can be activated like this:

First, find out the node id by using `docker ls`. Example:

..
    $ docker node ls
    ID                            HOSTNAME   STATUS    AVAILABILITY   MANAGER STATUS   ENGINE VERSION
    z676weq8fbp0qxvfmhr94zdh8     analyses   Ready     Active                          20.10.12
    viad94fqusn0invcaoz6r0orj     conengrk   Ready     Drain                           20.10.12
    c25vqccpuplkl94hcfk7ua3s6 *   topobank   Ready     Active         Leader           20.10.12

Here the node on the host "conengrk" has availability "Drain". Then activate:

.. code:: bash

    $ docker node update viad94fqusn0invcaoz6r0orj --availability active

Make sure the node has the current images needed, by calling `docker pull`.

Then, on the leader node, scale service `celeryworker` to 1, then 2. This ensures the worker container
runs on both nodes:

.. code:: bash

    $ docker service scale prodstack_celeryworker=1
    prodstack_celeryworker scaled to 1
    overall progress: 1 out of 1 tasks
    1/1: running   [==================================================>]
    verify: Service converged
    $ docker service scale prodstack_celeryworker=2
    prodstack_celeryworker scaled to 2
    overall progress: 2 out of 2 tasks
    1/2: running   [==================================================>]
    2/2: running   [==================================================>]
    verify: Service converged

Check with `docker service ls`. Example:

.. code:: bash

    $ docker service ls
    ID             NAME                     MODE         REPLICAS   IMAGE                                                              PORTS
    0sdeoxs3tg7h   prodstack_caddy          replicated   1/1        contact.engineering:5000/topobank_production_caddy:latest          *:80->80/tcp, *:443->443/tcp
    h82dqgjhh23r   prodstack_celerybeat     replicated   1/1        contact.engineering:5000/topobank_production_celerybeat:latest
    ibgfmdcclm6o   prodstack_celeryworker   replicated   2/2        contact.engineering:5000/topobank_production_celeryworker:latest
    2zsgtbz5w11h   prodstack_dbbackup       replicated   1/1        contact.engineering:5000/topobank_production_dbbackup:latest
    qblc2e4z8wng   prodstack_django         replicated   1/1        contact.engineering:5000/topobank_production_django:latest
    j1puk9h0plob   prodstack_postgres       replicated   1/1        contact.engineering:5000/topobank_production_postgres:latest
    07q7k3e2iuro   prodstack_redis          replicated   1/1        redis:6-alpine










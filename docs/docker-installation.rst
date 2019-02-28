

.. role:: bash(code)
   :language: bash


Install docker on Ubuntu 18.04
==============================

We want to have the latest version.
See also https://medium.com/devgorilla/how-to-install-docker-on-ubuntu-18-04-495216a16092 .

.. code:: bash

  sudo bash

As root then

.. code:: bash

  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
  sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable edge"

This adds a new package repository for docker into `/etc/apt/sources.list`.

.. code:: bash

  sudo apt-get install -y docker-ce

Check wether active docker is:

  sudo systemctl status docker

Add user to docker group:

  sudo usermod -aG docker ${USER}

Newest version!

docker-compose
--------------

Either directly as binary or via pip:

 pip install docker-compose


docker-machine
--------------

For installation of docker-machine follow

 https://docs.docker.com/machine/install-machine/


In order to get it working in PyCharm, i.e. creating a Run configuration for deployment,
see here

  https://intellij-support.jetbrains.com/hc/en-us/community/posts/360000174084-docker-compose-does-not-work-on-ubuntu-using-default-settings

- Go to Settings >> Build, Execution, Deployment >> Docker
- Select "TCP socket" (instead "Unix socket")
- Enter 'unix:///var/run/docker.sock' under "Engine API URL"


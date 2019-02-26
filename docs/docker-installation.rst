
Install docker on Ubuntu 18.04
==============================

We want to have the latest version.

https://medium.com/devgorilla/how-to-install-docker-on-ubuntu-18-04-495216a16092


curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable edge"


  sudo apt-get install -y docker-ce

Check wether aktive:

  sudo systemctl status docker

Add user to docker group:

  sudo usermod -aG docker ${USER}

Newest version!

docker-compose
--------------

Either directly as binary or via pip:

 pip install docker-compose


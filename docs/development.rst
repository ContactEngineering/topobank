
Development
===========

Use a virtual environment
-------------------------

For everything listed here, use a virtual environemt,
which can be generated e.g. via

.. code:: bash

    python -m venv ./venv

in the project's main directory. Activate with

.. code:: bash

    . venv/bin/activate


How to update requirements
--------------------------

The requirements are defined in `setup.cfg`.
Under `install_requires = ` everything is listed
for running the application in production.
In the section

.. code::

    [options.extras_require]
    dev =

all additional dependencies are listed which are needed for development.

In order to generate requirements files, which are used e.g. in the Docker files, enter
the `requirements` directory and call `make`.
Make sure the virtual environment is activated.

Afterwards, the local environment can be updated using

.. code:: bash

    $ pip install -r requirements/local.txt






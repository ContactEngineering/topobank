

Login via ORCID
===============

Getting an ORCID account
------------------------

Each user must have an `ORCID <https://orcid.org>`_ account in order to use the TopoBank application.

Register a Public API Client
----------------------------

For running Topobank, you need to register a public API client on the ORCID website
for the following purposes:

- get a client API + secrect in order to be able to authenticate against orcid.org
- set a redirect URL to which Topobank will redirect after successful authentication
- the TopoBank website is listed (TODO check where is this, or only true for members?)

See `here <https://support.orcid.org/hc/en-us/articles/360006897174>`_ for more information
how to do it.

You need the generated client ID and client secret for the next step.

As redirect URL add all of these

- for development: http://127.0.0.1:8000/accounts/orcid/login/callback
- for development: http://localhost:8000/accounts/orcid/login/callback
- for production: https://topobank.contact.engineering/accounts/orcid/login/callback

One of the redirect URL configured at orcid.org must exactly match the redirect URL, which is
transferred from the TopoBank application during the login process.
This means, if you use

 http://localhost:8000

i.e. `localhost` instead of `127.0.0.1` during development, you'll need also redirect url with `localhost` which is

 http://localhost:8000/accounts/orcid/login/callback

If you have both `localhost` and `127.0.0.1`, it shoudn't matter.


Configure TopoBank with Client ID and Secrect Key
-------------------------------------------------

If you use Docker, edit the config files

::

   .envs/.local/.django
   .envs/.production/.django

and set the correct values in the variables
::

   ORCID_CLIENT_ID
   ORCID_SECRET

Adding ORCID provider with access information
---------------------------------------------

In order to connect to the orcid service, you have to
generate an entry in the local database which holds acccess information
like a client id and a client secret. This shows the ORCID
website that our site is allowed to use the autentication services of ORCID.

Manually using a database tool or django admin
..............................................

In order to do so, you have several ways. During development you can use an external database tool (e.g. SQLite Browser)
to edit your user account in table `users_user`. Set `is_staff` and `is_superuser` to True.

Enter the URL
::

  localhost:8000/admin

(if in development) and login with your credentials.

Create an entry in the table `socialaccount_socialapp` filling the following fields:
::

    Provider: orcid.org
    Name: ORCID
    Client ID: <use the one from ORCID website>
    Secret: <use the one from ORCID website>

Recommended: Import database entry via command line tool
........................................................

Use the template file `orcid.yaml.template` which looks like this:
::

    - model: "socialaccount.socialapp"
      pk: 1
      fields:
         provider: orcid
         name: ORCID
         client_id: ${ORCID_CLIENT_ID}
         secret: ${ORCID_SECRET}
         key: ""
         sites: [1]

Copy to `orcid.yaml` and replace `${ORCID_CLIENT_ID}` and `${ORCID_SECRET}` with the corresponding values.
This can be done automatically through environment variables by using the tool `envsubst`:
::

   envsubst < orcid.yaml.template > orcid.yaml

See the section :ref:`first-run` how to do this in a docker container.






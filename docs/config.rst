

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

As redirect URL add all of these

- for development: http://127.0.0.1:8000/accounts/orcid/login/callback
- for development: http://localhost:8000/accounts/orcid/login/callback
- for production: https://topobank.contact.engineering/accounts/orcid/login/callback

You need the generated client ID and client secret for the next step.

Configure TopoBank with Client ID and Secrect Key
-------------------------------------------------

If you use Docker, edit the config files

   .envs/.local/.django
   .envs/.production/.django

and set the correct values in the variables

   ORCID_CLIENT_ID
   ORCID_SECRET




Redirect URL pointing to localhost
----------------------------------

The redirect URL configured at orcid.org must exactly match the redirect URL, which is
transferred from the TopoBank application during the login process.
This means, if you use

 http://localhost:8000

i.e. `localhost` instead of `127.0.0.1`, you'll need also a redirect url with `localhost` which is

 http://localhost:8000/accounts/orcid/login/callback


Adding ORCID provider with access information
---------------------------------------------

In order to connect to the orcid service, you have to
generate an entry in the local database which holds acccess information
like a client id and a client secret. This shows the ORCID
website that our site is allowed to use the autentication services of ORCID.

In order to do so, use an external database tool (e.g. SQLite Browser)
to edit your user account in table `users_user`. Set `is_staff`
and `is_superuser` to True.

TODO only allow local use of admin

Enter the URL

 localhost:8000/admin

(if in development) and login with your credentials.

TODO provide a commandline line tool in order to add ORCID credentials.


Provider: orcid.org
Name: ORCID
Client ID: ..
Secret: ..



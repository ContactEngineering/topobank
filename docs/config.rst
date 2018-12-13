

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

As redirect URL take

- for development: http://127.0.0.1:8000/accounts/orcid/login/callback
- for production: **to be defined**

You need the generated client ID and client secret for the next step.

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





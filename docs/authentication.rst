Authentication
==============

Users can sign in to TopoBank in three ways:

- with an `ORCID <https://orcid.org>`_ account,
- with a Google account,
- with an email address and a password.

Several of these can be connected to the same account. Somebody who registered
with an email address can add their ORCID iD later, and the connected
identities are listed on the *Connected identities* page (``/accounts/3rdparty/``).
An identity can also be disconnected again, as long as one way of signing back
in remains.

.. _orcid-required-for-publication:

ORCID is required for publishing
--------------------------------

Publishing a dataset creates an immutable, citable record with a DOI, and the
authors of such a record have to be identifiable as researchers. TopoBank
therefore refuses to publish for a user who has no ORCID account connected.
Everything else -- uploading, analyzing, sharing -- works with any of the
sign-in methods.

The rule is enforced on the publication endpoints themselves, not only in the
user interface, so it also applies to API clients. The user interface explains
the requirement before a publication form is filled in, and links to the page
where the ORCID account can be connected.

Login with ORCID
----------------

Register a Public API Client
............................

For running TopoBank, you need to register a public API client on the ORCID website
for the following purposes:

- get a client API + secret in order to be able to authenticate against orcid.org
- set a redirect URL to which TopoBank will redirect after successful authentication
- the TopoBank website is listed (TODO check where is this, or only true for members?)

See `here <https://support.orcid.org/hc/en-us/articles/360006897174>`_ for more information
how to do it.

You need the generated client ID and client secret for the next step.

As redirect URL add all of these

- for development: http://127.0.0.1:8000/accounts/orcid/login/callback
- for development: http://localhost:8000/accounts/orcid/login/callback
- for production: https://topobank.contact.engineering/accounts/orcid/login/callback

One of the redirect URLs configured at orcid.org must exactly match the redirect URL, which is
transferred from the TopoBank application during the login process.
This means, if you use

 http://localhost:8000

i.e. `localhost` instead of `127.0.0.1` during development, you'll need also redirect url with `localhost` which is

 http://localhost:8000/accounts/orcid/login/callback

If you have both `localhost` and `127.0.0.1`, it shouldn't matter.


Configure TopoBank with Client ID and Secret Key
................................................

If you use Docker, edit the config files

::

   .envs/.local/.django
   .envs/.production/.django

and set the correct values in the variables
::

   ORCID_CLIENT_ID
   ORCID_SECRET

Adding the ORCID provider with access information
.................................................

In order to connect to the ORCID service, you have to
generate an entry in the local database which holds access information
like a client id and a client secret. This shows the ORCID
website that our site is allowed to use the authentication services of ORCID.

Manually using a database tool or django admin
,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,

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
,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,

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

Then this entry must be imported into the database::

   python manage.py loaddata orcid.yaml

See the section :ref:`first-run` how to do this in a docker container.

Login with Google
-----------------

Google works the same way: register an OAuth client, then store its credentials
in the database as a second ``socialaccount.socialapp`` entry.

Register an OAuth client
........................

In the `Google Cloud console <https://console.cloud.google.com/apis/credentials>`_,
create an *OAuth 2.0 Client ID* of type *Web application* and configure its
authorized redirect URIs:

- for development: http://127.0.0.1:8000/accounts/google/login/callback/
- for development: http://localhost:8000/accounts/google/login/callback/
- for production: https://topobank.contact.engineering/accounts/google/login/callback/

As with ORCID, the redirect URI must match exactly, including the trailing
slash and the host name you actually browse to.

The OAuth consent screen needs the ``email`` and ``profile`` scopes; those are
the only ones TopoBank asks for, and they are what fills in the name and email
address of a newly created account.

Configure TopoBank with Client ID and Secret Key
................................................

Set the variables
::

   GOOGLE_CLIENT_ID
   GOOGLE_SECRET

and import them the same way as for ORCID, using the template file
`google.yaml.template`::

   envsubst < google.yaml.template > google.yaml
   python manage.py loaddata google.yaml

Login with email and password
-----------------------------

Local accounts need no provider configuration; the sign-up form is reachable
from the login page. Two settings govern them:

``ACCOUNT_ALLOW_SIGNUP``
   Whether the site accepts registrations for local accounts at all. Defaults
   to ``True``. Switching it off leaves ORCID and Google sign-in untouched.

``ACCOUNT_EMAIL_VERIFICATION``
   Whether a newly registered address has to be confirmed before the account
   can be used. Defaults to ``mandatory``, which requires a working outgoing
   mail configuration. Set it to ``none`` for a development instance that
   cannot send mail.

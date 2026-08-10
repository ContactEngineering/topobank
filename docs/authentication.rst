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

Which providers a deployment actually offers depends on two things: the
django-allauth provider app has to be in ``INSTALLED_APPS`` (ce-ui registers
ORCID and Google), and a ``socialaccount.socialapp`` row carrying the client
credentials has to exist for it. A provider missing either is simply not shown
on the sign-in page, so the sections below have to be followed for every
provider you want to offer.

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

- get a client ID + secret in order to be able to authenticate against orcid.org
- set a redirect URL to which TopoBank will redirect after successful authentication

A free ORCID account is enough to register a public API client: there is no
review to pass and no membership to buy. See
`here <https://support.orcid.org/hc/en-us/articles/360006897174>`_ for more
information how to do it.

You need the generated client ID and client secret for the next step.

As redirect URL add all of these

- for development: http://127.0.0.1:8000/accounts/orcid/login/callback/
- for development: http://localhost:8000/accounts/orcid/login/callback/
- for production: https://contact.engineering/accounts/orcid/login/callback/

One of the redirect URLs configured at orcid.org must exactly match the redirect URL, which is
transferred from the TopoBank application during the login process. django-allauth builds that
URL by reversing its callback route, so it always carries the **trailing slash** shown above;
a registered URL without one is rejected as a mismatch.

The host has to match exactly as well, so if you browse to

 http://localhost:8000

i.e. `localhost` instead of `127.0.0.1` during development, you'll need also a redirect url with `localhost` which is

 http://localhost:8000/accounts/orcid/login/callback/

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

    Provider: orcid
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

What you need before you start
..............................

An ordinary Google account and a Google Cloud project. Both are free: a Cloud
project needs **no billing account**, because sign-in is not a billable API,
and there is no paid developer programme to join.

Because TopoBank asks only for the ``email`` and ``profile`` scopes (plus
``openid``, which django-allauth adds), which Google classifies as
*non-sensitive*, the app **does not have to pass Google's OAuth verification
review** and needs no third-party security assessment. That changes the moment
a sensitive or restricted scope is added — Gmail, Drive, Calendar and the like
— so do not widen ``SOCIALACCOUNT_PROVIDERS["google"]["SCOPE"]`` without
budgeting several weeks for review.

One piece of validation is required: the domain you enter on the consent
screen has to be one whose ownership you have proven in
`Google Search Console <https://search.google.com/search-console>`_, via a DNS
record or an uploaded file. This is a one-off and takes minutes.

Configure the consent screen
............................

In the Google Cloud console, under *Google Auth Platform* (older versions of
the console call this *APIs & Services* → *OAuth consent screen*), configure:

- user type *External*, since users sign in with their own Google accounts
- the application name and the support and developer contact addresses
- links to the privacy policy and the terms and conditions
- ``contact.engineering`` as an authorized domain (see the domain verification
  above)
- the ``email`` and ``profile`` scopes, and nothing else

.. important::

   A newly configured *External* app starts in publishing status **Testing**,
   which only lets the up-to-100 accounts on its test-user list sign in, and
   **expires every authorization after seven days**. Left in that state,
   sign-in silently stops working for your testers a week later. Press
   *Publish app* to move the app to *In production*; with non-sensitive scopes
   only, that transition does not trigger a review.

If you want TopoBank's name and logo to appear on Google's consent screen
rather than only the domain, complete Google's *brand verification*. It is a
lighter-weight process than scope verification and is not a prerequisite for
sign-in to work.

Register an OAuth client
........................

In the `Google Cloud console <https://console.cloud.google.com/apis/credentials>`_,
create an *OAuth 2.0 Client ID* of type *Web application* and configure its
authorized redirect URIs:

- for development: http://127.0.0.1:8000/accounts/google/login/callback/
- for development: http://localhost:8000/accounts/google/login/callback/
- for production: https://contact.engineering/accounts/google/login/callback/

As with ORCID, the redirect URI must match exactly, including the trailing
slash and the host name you actually browse to. Google exempts ``localhost``
from its HTTPS requirement, so a plain ``http://`` redirect URI is accepted for
development — but ``localhost`` cannot be used as an *authorized domain* on the
consent screen.

The client ID and client secret are shown once the client is created, and can
be downloaded again from the same page afterwards.

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
from the login page. A registration asks for a name, a username, an email
address and a password, and the account can then sign in with either the
username or the address (``ACCOUNT_LOGIN_METHODS``).

Two settings govern local accounts:

``ACCOUNT_ALLOW_SIGNUP``
   Whether the site accepts registrations for local accounts at all. Defaults
   to ``True``. Switching it off leaves ORCID and Google sign-in untouched.

``ACCOUNT_EMAIL_VERIFICATION``
   Whether a newly registered address has to be confirmed before the account
   can be used. Defaults to ``mandatory``, which requires a working outgoing
   mail configuration. Set it to ``none`` for a development instance that
   cannot send mail.

Note that an address is mandatory for a *local* registration but not for a
social one: ORCID does not necessarily release an email address, and requiring
one would turn a working sign-in into a form to fill in. This is why
``SOCIALACCOUNT_EMAIL_REQUIRED`` is set to ``False`` explicitly — django-allauth
would otherwise derive it from the local signup fields.

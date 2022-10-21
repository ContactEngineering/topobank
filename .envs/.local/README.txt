Settings for local development
------------------------------

Generate "".pypi-authfile" in this directory by

$ sudo apt install apache2-utils
$ htpasswd -sc ".pypi-authfile" "topobank"
  (enter new password twice)

For values of PYPI_SERVER_UID and PYPI_SERVER_GID use
`id` on the command line.

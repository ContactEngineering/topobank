FROM continuumio/miniconda3
# FROM ubuntu:18.04
#FROM python:3.7-alpine

ENV PYTHONUNBUFFERED 1

#
# System dependencies for Python + Django
#
# TODO maybe in one command?
RUN apt-get update \
  && apt-get install --yes libfftw3-3 libfftw3-dev gcc g++ gettext

# clean up image
#RUN apt-get -qy autoremove

#
# Create target directory
#
#ARG topobankdir=/app
#RUN mkdir -p ${topobankdir}
#WORKDIR ${topobankdir}

#
# Installation of PyCo + dependencies
#
# Copy PyCo source code into container, uncompress
COPY PyCo-0.31.0.tar.gz .
RUN tar xfvz PyCo-0.31.0.tar.gz
WORKDIR PyCo-0.31.0

# install additional PyCo dependencies
RUN pip install wheel
RUN pip install -r requirements.txt

# install PyCo itself in venv
RUN pip install .


#
# Install requirements for TopoBank
#
# TODO move to top
# Pillow requirements
RUN apt-get install --yes libjpeg-dev zlib1g-dev libfreetype6-dev liblcms2-dev libtiff-dev tk-dev tcl-dev librabbitmq-dev

COPY ./requirements /requirements
WORKDIR /
RUN pip install -r /requirements/local.txt
RUN pip install celery-flower
# TODO add celery flower to app requirements
RUN pip install -r /requirements/test.txt
# TODO remove test settings as they are always useful for local?

# Here the entrypoint from production settings is taken!
COPY ./compose/production/django/entrypoint /entrypoint
RUN sed -i 's/\r//' /entrypoint
RUN chmod +x /entrypoint

COPY ./compose/local/django/start /start
RUN sed -i 's/\r//' /start
RUN chmod +x /start

COPY ./compose/local/django/celery/worker/start /start-celeryworker
RUN sed -i 's/\r//' /start-celeryworker
RUN chmod +x /start-celeryworker

COPY ./compose/local/django/celery/beat/start /start-celerybeat
RUN sed -i 's/\r//' /start-celerybeat
RUN chmod +x /start-celerybeat

COPY ./compose/local/django/celery/flower/start /start-flower
RUN sed -i 's/\r//' /start-flower
RUN chmod +x /start-flower

RUN addgroup django \
    && adduser --ingroup django --gecos "" --disabled-password django
# or using --system? Problems with permissions?
# celeryworker should not run as root, refuses to work
#
# TODO use --disabled-login ??

#
# Prepare application code
#
COPY . /app
RUN chown -R django /app
# is the following needed?
RUN chmod -R u+w /app

#
# Prepare some system settings
#
# RUN sysctl vm.overcommit_memory=1
# TODO needed for redis to suppress warning, but in which package?

#
# Finalize..
#
WORKDIR /app

USER django

ENTRYPOINT ["/entrypoint"]

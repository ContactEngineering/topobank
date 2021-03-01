FROM continuumio/miniconda3
# FROM ubuntu:18.04
#FROM python:3.7-alpine

ENV PYTHONUNBUFFERED 1
ENV CFLAGS "-I/usr/include/eigen3/"
# This is a workaround for https://gitlab.com/muspectre/muspectre/-/issues/144

#
# System dependencies for Python + Django
#
RUN apt-get update \
  && apt-get install --yes apt-utils \
  && apt-get install --yes libfftw3-3 libfftw3-dev libopenblas-dev libeigen3-dev gcc g++ gettext \
  # Pillow requirements
  && apt-get install --yes libjpeg-dev zlib1g-dev libfreetype6-dev \
     liblcms2-dev libtiff-dev tk-dev tcl-dev librabbitmq-dev \
  # Requirements in order to built libmufft
  # (curl is used to download pybind11 and Eigen3)
  && apt-get install --yes curl \
  # && apt-get install --yes mpicc libfftw3-mpi-dev
  # && apt-get install --yes clang-5 libfftw3-dev
  && apt-get install --yes libmemcached-dev
  # Requirement needed for exporting bokeh plots

# clean up image
RUN apt-get -qy autoremove

#
# Extra requirements for exporting plots in bokeh
#
RUN apt-get install --yes libgtk-3-0 libdbus-glib-1-2
RUN conda install -c conda-forge firefox geckodriver

#
# Install requirements for TopoBank
#
COPY ./requirements /requirements
WORKDIR /
RUN pip install -r /requirements/local.txt --ignore-installed
RUN pip install -r /requirements/test.txt --ignore-installed
# TODO remove test requirements as they are always useful for local?

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
# TODO check, can we use --disabled-login ??

#
# Prepare application code
#
COPY . /app
RUN chown -R django /app
# is the following needed?
RUN chmod -R u+w /app

#
# Finalize..
#
WORKDIR /app

USER django

ENTRYPOINT ["/entrypoint"]

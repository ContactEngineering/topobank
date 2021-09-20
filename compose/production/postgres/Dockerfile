FROM postgres:13.4

# The docker image automatically creates user+password+database if the appropriate
# environment variables are set, see here:
#  https://docs.docker.com/samples/library/postgres/

COPY ./compose/production/postgres/maintenance /usr/local/bin/maintenance
RUN chmod +x /usr/local/bin/maintenance/*
RUN mv /usr/local/bin/maintenance/* /usr/local/bin \
    && rmdir /usr/local/bin/maintenance

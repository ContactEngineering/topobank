FROM codestation/postgres-s3-backup

ARG RESTORE_DATABASE=0
ENV RESTORE_DATABASE=$RESTORE_DATABASE
# Set RESTORE_DATABASE to 1 in environment in order to restore
# the database.

COPY ./compose/production/dbbackup/entrypoint /entrypoint
RUN sed -i 's/\r//' /entrypoint
RUN chmod +x /entrypoint

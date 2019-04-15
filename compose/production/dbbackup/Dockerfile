FROM codestation/postgres-s3-backup

COPY ./compose/production/dbbackup/entrypoint /entrypoint
RUN sed -i 's/\r//' /entrypoint
RUN chmod +x /entrypoint

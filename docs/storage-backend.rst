Storage Backend
---------------

Using Minio client in Docker image to test connection.

$ docker run -it --entrypoint=/bin/sh minio/mc

Adding S3 host:

/ # mc config host add rz-uni-freiburg https://s3gw1.vm.privat:8082/ <Access Key ID> <Secret Access Key> --insecure

Problem so far: Certificate is not valid: "

/ # mc ls rz-uni-freiburg
mc: <ERROR> Unable to list folder. Get https://s3gw1.vm.privat:8082/: x509: certificate is valid for 12254640, not s3gw1.vm.privat

With --insecure it works:

/ # mc ls rz-uni-freiburg --insecure

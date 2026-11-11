# MLflow needs a PostgreSQL driver and an S3 client, which the official image
# does not bundle. The version is pinned to the server release.
FROM ghcr.io/mlflow/mlflow:v3.18.0

RUN pip install --no-cache-dir \
    psycopg2-binary==2.9.13 \
    boto3==1.44.0

USER 1000:1000
EXPOSE 5000

CMD ["mlflow", "server", "--host", "0.0.0.0", "--port", "5000"]

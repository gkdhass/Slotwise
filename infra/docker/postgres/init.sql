-- PostgreSQL initialisation. Runs once on an empty data volume.
-- MLflow keeps its metadata in a separate database from operational records.
CREATE DATABASE mlflow;

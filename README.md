# Airflow

## Setup dag().test()
- Ensure containers are running
- Ensure working directory is set to the root of the project
- Add environment variable in run configuration: `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:airflow@<HOST_IP>:5432/airflow`

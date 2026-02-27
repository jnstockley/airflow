FROM apache/airflow:slim-3.1.7 AS build

COPY requirements.txt .

USER root

RUN sudo apt-get update -y && \
    sudo apt-get install -y build-essential python3-dev libpq-dev

USER airflow

RUN pip3 install --upgrade pip && \
    pip3 install -r requirements.txt

FROM apache/airflow:slim-3.1.7

COPY --from=build home/airflow/.local/ /home/airflow/.local/

ENV PYTHONPATH="${PYTHONPATH}:/opt/airflow/plugins" \
    PATH="/home/airflow/.local/bin:${PATH}" \
    AIRFLOW__CORE__EXECUTOR=LocalExecutor \
    AIRFLOW__CORE__AUTH_MANAGER=airflow.providers.fab.auth_manager.fab_auth_manager.FabAuthManager \
    AIRFLOW__SCHEDULER__ENABLE_HEALTH_CHECK=True \
    AIRFLOW__CORE__LOAD_EXAMPLES=False \
    AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=True \
    AIRFLOW__SCHEDULER__MIN_FILE_PROCESS_INTERVAL=10 \
    AIRFLOW__CORE__EXECUTION_API_SERVER_URL=http://airflow-apiserver:8080/execution/ \
    FORWARDED_ALLOW_IPS=* \
    AIRFLOW__FAB__ENABLE_PROXY_FIX=True \
    AIRFLOW__CORE__DEFAULT_TIMEZONE=America/Chicago \
    AIRFLOW__CORE__DEFAULT_TASK_EXECUTION_TIMEOUT=3600 \
    AIRFLOW__FAB__COOKIE_SECURE=True \
    AIRFLOW__FAB__COOKIE_SAMESITE=Strict \
    TZ=America/Chicago \
    AIRFLOW__CORE__AUTH_MANAGER=webserver_config.AuthentikAuthManager

COPY config/webserver_config.py /opt/airflow

COPY plugins /opt/airflow/plugins

COPY dags /opt/airflow/dags

USER root

RUN chmod -R 770 /opt/airflow

USER airflow

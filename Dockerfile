FROM dhi.io/airflow:3.1.7-dev AS build

COPY requirements.txt .

RUN pip3 install --upgrade pip && \
    pip3 install --user -r requirements.txt

FROM dhi.io/airflow:3.1.7

COPY --from=build /root/.local/ /home/airflow/.local/

ENV PYTHONPATH "${PYTHONPATH}:/opt/airflow/plugins"

ENV PATH="/home/airflow/.local/bin:${PATH}" \
    AIRFLOW__CORE__EXECUTOR=LocalExecutor \
    AIRFLOW__CORE__AUTH_MANAGER=airflow.providers.fab.auth_manager.fab_auth_manager.FabAuthManager \
    AIRFLOW__SCHEDULER__ENABLE_HEALTH_CHECK='true' \
    AIRFLOW__CORE__LOAD_EXAMPLES='false'\
    AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION='true' \
    AIRFLOW__SCHEDULER__MIN_FILE_PROCESS_INTERVAL=10

COPY config/webserver_config.py /opt/airflow

COPY plugins /opt/airflow/plugins

COPY dags /opt/airflow/dags

USER airflow
